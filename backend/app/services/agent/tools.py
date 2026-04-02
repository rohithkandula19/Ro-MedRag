"""
Agent Tools — the capabilities the agent can invoke.

Each tool is a standalone function that reads from AgentState and writes back.
Tools are used by LangGraph nodes but are decoupled for testability.
"""

import asyncio
from typing import List, Optional

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.services.agent.state import AgentState, RetrievedChunk

logger = get_logger(__name__)


# ── Retrieval Tool ────────────────────────────────────────────────────────────

class RetrievalTool:
    """
    Semantic search over the FAISS vector store.
    Supports scoped search (by document_ids) and relevance filtering.
    """

    def __init__(self, embedder, vector_store, reranker):
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

    async def retrieve(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
        top_k_retrieve: int = settings.TOP_K_RETRIEVAL,
        top_k_rerank: int = settings.TOP_K_RERANK,
        min_score: float = settings.MIN_RELEVANCE_SCORE,
    ) -> List[RetrievedChunk]:
        """Embed query → FAISS search → filter → rerank → return chunks."""

        # 1. Embed the query
        query_embedding = await self.embedder.embed_query(query)

        # 2. Search vector store
        raw_results = self.vector_store.search(query_embedding, top_k=top_k_retrieve)

        # 3. Scope to specific documents if requested
        if document_ids:
            raw_results = [r for r in raw_results if r["document_id"] in document_ids]

        # 4. Filter by relevance threshold
        raw_results = [r for r in raw_results if r["score"] >= min_score]

        if not raw_results:
            return []

        # 5. Rerank
        reranked = self.reranker.rerank(query, raw_results, top_k=top_k_rerank)

        # 6. Convert to RetrievedChunk objects
        chunks = [
            RetrievedChunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                document_filename=r["document_filename"],
                content=r["content"],
                page_number=r.get("page_number"),
                relevance_score=r["score"],
                citation_index=i + 1,
            )
            for i, r in enumerate(reranked)
        ]

        return chunks


# ── Query Reformulation Tool ─────────────────────────────────────────────────

class QueryReformulationTool:
    """
    When initial retrieval is insufficient, reformulate the query.
    Uses the LLM to generate a better search query based on:
      - The original question
      - What was (poorly) retrieved
      - Conversation history for context
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    async def reformulate(
        self,
        original_query: str,
        retrieved_chunks: List[RetrievedChunk],
        attempt: int,
        conversation_context: str = "",
    ) -> str:
        """Generate a reformulated search query."""

        retrieved_summary = ""
        if retrieved_chunks:
            retrieved_summary = "\n".join(
                f"- {c.document_filename} (score {c.relevance_score:.2f}): {c.content[:100]}..."
                for c in retrieved_chunks[:3]
            )

        prompt = f"""You are a medical research query optimizer. The following search query 
did not retrieve sufficiently relevant results from a medical document database.

ORIGINAL QUERY: {original_query}

ATTEMPT: {attempt} of 3

{f'CONVERSATION CONTEXT: {conversation_context}' if conversation_context else ''}

{f'WHAT WAS RETRIEVED (low relevance):{chr(10)}{retrieved_summary}' if retrieved_summary else 'NOTHING was retrieved.'}

Generate a SINGLE reformulated search query that:
1. Uses different medical terminology or synonyms
2. Is more specific if the original was too broad
3. Is broader if the original was too narrow
4. Focuses on the core medical concept

Respond with ONLY the reformulated query, nothing else."""

        reformulated, _ = await self.llm.generate(prompt, max_tokens=100)
        return reformulated.strip().strip('"')


# ── Comparison Tool ──────────────────────────────────────────────────────────

class ComparisonTool:
    """
    Compares findings across multiple documents or topics.
    Used when the agent detects a comparative query like:
      "Compare treatment A vs treatment B"
      "What do different papers say about X?"
    """

    def __init__(self, retrieval_tool: RetrievalTool):
        self.retrieval = retrieval_tool

    async def compare(
        self,
        query: str,
        subjects: List[str],
        document_ids: Optional[List[str]] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve chunks for each comparison subject and merge results."""

        all_chunks = []
        seen_chunk_ids = set()

        for subject in subjects:
            # Search for each subject separately
            search_query = f"{query} {subject}"
            chunks = await self.retrieval.retrieve(
                search_query,
                document_ids=document_ids,
                top_k_retrieve=6,
                top_k_rerank=3,
            )

            for chunk in chunks:
                if chunk.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.chunk_id)
                    all_chunks.append(chunk)

        # Re-index citations
        for i, chunk in enumerate(all_chunks):
            chunk.citation_index = i + 1

        return all_chunks


# ── Data Extraction Tool ─────────────────────────────────────────────────────

class DataExtractionTool:
    """
    Extracts structured data from retrieved chunks.
    Used for queries like:
      "What are the dosage recommendations?"
      "List all side effects mentioned"
      "Extract the inclusion criteria"
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    async def extract(
        self,
        query: str,
        chunks: List[RetrievedChunk],
    ) -> str:
        """Use LLM to extract structured data from chunks."""

        context = "\n\n---\n\n".join(
            f"[{c.citation_index}] (Source: {c.document_filename}, Page {c.page_number or 'N/A'}):\n{c.content}"
            for c in chunks
        )

        prompt = f"""You are a medical data extraction specialist. Extract structured information 
from the provided medical literature context.

CONTEXT:
{context}

EXTRACTION REQUEST: {query}

Instructions:
- Extract ONLY information present in the context above.
- Use inline citations [1], [2], etc. for every extracted data point.
- Organize data in a clear, structured format (tables, lists, or categories as appropriate).
- If specific data is not available, note "Not found in provided documents."
- End with: "⚠️ This is not medical advice. Consult a qualified healthcare professional."

EXTRACTED DATA:"""

        return prompt


# ── Sufficiency Evaluator ────────────────────────────────────────────────────

class SufficiencyEvaluator:
    """
    Evaluates whether retrieved chunks are sufficient to answer the query.
    This drives the agent's decision to re-query or proceed to generation.
    """

    def evaluate(
        self,
        query: str,
        chunks: List[RetrievedChunk],
        min_chunks: int = 2,
        min_avg_score: float = 0.4,
    ) -> bool:
        """
        Returns True if retrieval is sufficient to answer the query.

        Criteria:
          1. At least min_chunks retrieved
          2. Average relevance score above threshold
          3. At least one chunk with high relevance (>0.5)
        """
        if not chunks:
            return False

        if len(chunks) < min_chunks:
            return False

        avg_score = np.mean([c.relevance_score for c in chunks])
        if avg_score < min_avg_score:
            return False

        has_high_relevance = any(c.relevance_score > 0.5 for c in chunks)
        if not has_high_relevance:
            return False

        return True


# ── Answer Validator ─────────────────────────────────────────────────────────

class AnswerValidator:
    """
    Self-correction: validates that the generated answer is grounded in sources.

    Checks:
      1. Every citation reference [N] maps to an actual retrieved chunk
      2. No claims appear to be fabricated (not traceable to any chunk)
      3. The "INSUFFICIENT_EVIDENCE" keyword is used appropriately
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    async def validate(
        self,
        answer: str,
        chunks: List[RetrievedChunk],
        query: str,
    ) -> tuple[bool, List[str]]:
        """
        Returns (is_valid, list_of_issues).
        """
        issues = []

        # Check 1: Citation references exist
        import re
        cited_indices = set(int(m) for m in re.findall(r"\[(\d+)\]", answer))
        available_indices = set(c.citation_index for c in chunks)
        phantom_citations = cited_indices - available_indices
        if phantom_citations:
            issues.append(f"Phantom citations referenced: {phantom_citations}")

        # Check 2: If answer is substantial, it should have citations
        if len(answer) > 200 and not cited_indices and "INSUFFICIENT_EVIDENCE" not in answer:
            issues.append("Answer has no citations despite being substantive")

        # Check 3: Use LLM to verify grounding (lightweight check)
        if not issues and chunks:
            grounding_check = await self._llm_grounding_check(answer, chunks, query)
            if not grounding_check:
                issues.append("LLM grounding check failed — answer may contain unsupported claims")

        return len(issues) == 0, issues

    async def _llm_grounding_check(
        self,
        answer: str,
        chunks: List[RetrievedChunk],
        query: str,
    ) -> bool:
        """Quick LLM check: is the answer grounded in the provided sources?"""

        context_summary = "\n".join(
            f"[{c.citation_index}]: {c.content[:200]}..."
            for c in chunks[:4]
        )

        prompt = f"""You are a fact-checking assistant. Determine if the following answer 
is fully grounded in the provided source material.

SOURCES:
{context_summary}

ANSWER TO CHECK:
{answer[:500]}

Is every factual claim in the answer supported by the sources above?
Respond with ONLY "YES" or "NO"."""

        result, _ = await self.llm.generate(prompt, max_tokens=10)
        return "YES" in result.upper()
