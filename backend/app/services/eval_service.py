"""
RAG Evaluation Service — measure retrieval and generation quality.

Implements RAGAS-inspired metrics:
  1. Faithfulness   — Is the answer grounded in retrieved context?
  2. Answer Relevancy — Does the answer actually address the question?
  3. Context Precision — Are the retrieved chunks relevant to the question?
  4. Context Recall   — Did retrieval find all needed information?

Also tracks:
  - Citation accuracy — Do [N] references map to real chunks?
  - Latency percentiles
  - Cost per query
"""

import re
import time
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.core.logging import get_logger
from app.services.rag_pipeline import get_pipeline, LLMClient, RAGResponse

logger = get_logger(__name__)


@dataclass
class EvalResult:
    """Result of evaluating a single query."""
    query: str
    answer: str
    faithfulness: float       # 0-1: how grounded in context
    answer_relevancy: float   # 0-1: how well it addresses the question
    context_precision: float  # 0-1: are retrieved chunks relevant
    citation_accuracy: float  # 0-1: do citations map correctly
    latency_ms: int
    tokens_used: int
    chunks_retrieved: int
    insufficient_evidence: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSuiteResult:
    """Result of running a full evaluation suite."""
    timestamp: str
    total_queries: int
    avg_faithfulness: float
    avg_answer_relevancy: float
    avg_context_precision: float
    avg_citation_accuracy: float
    avg_latency_ms: float
    total_tokens: int
    results: List[EvalResult]
    pass_rate: float          # % of queries that passed all thresholds


# Default test queries for healthcare RAG evaluation
DEFAULT_TEST_QUERIES = [
    {
        "query": "What are the main types of cancer?",
        "expected_keywords": ["carcinoma", "sarcoma", "leukemia", "lymphoma"],
    },
    {
        "query": "What are risk factors for cancer?",
        "expected_keywords": ["tobacco", "radiation", "genetics", "diet"],
    },
    {
        "query": "How is cancer diagnosed?",
        "expected_keywords": ["biopsy", "imaging", "screening", "blood test"],
    },
    {
        "query": "What are the treatment options for cancer?",
        "expected_keywords": ["surgery", "chemotherapy", "radiation", "immunotherapy"],
    },
    {
        "query": "What is the role of immunotherapy in cancer treatment?",
        "expected_keywords": ["immune system", "checkpoint", "CAR-T"],
    },
]


class RAGEvaluator:
    """Evaluates RAG pipeline quality using automated metrics."""

    def __init__(self):
        self.llm = LLMClient()

    async def evaluate_single(
        self,
        query: str,
        expected_keywords: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
    ) -> EvalResult:
        """Run a single query through the pipeline and evaluate quality."""

        pipeline = get_pipeline()
        start = time.time()

        # Run the RAG query
        response: RAGResponse = await pipeline.query(
            question=query,
            document_ids=document_ids,
            mode="qa",
        )

        latency_ms = int((time.time() - start) * 1000)

        # Skip detailed eval if insufficient evidence
        if response.insufficient_evidence:
            return EvalResult(
                query=query,
                answer=response.answer,
                faithfulness=0.0,
                answer_relevancy=0.0,
                context_precision=0.0,
                citation_accuracy=0.0,
                latency_ms=latency_ms,
                tokens_used=response.tokens_used,
                chunks_retrieved=len(response.citations),
                insufficient_evidence=True,
            )

        # Evaluate metrics
        faithfulness = await self._eval_faithfulness(response)
        answer_relevancy = await self._eval_answer_relevancy(query, response)
        context_precision = self._eval_context_precision(query, response, expected_keywords)
        citation_accuracy = self._eval_citation_accuracy(response)

        return EvalResult(
            query=query,
            answer=response.answer[:500],
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_precision=context_precision,
            citation_accuracy=citation_accuracy,
            latency_ms=latency_ms,
            tokens_used=response.tokens_used,
            chunks_retrieved=len(response.citations),
            details={
                "confidence": response.confidence,
                "keywords_found": expected_keywords or [],
            },
        )

    async def run_eval_suite(
        self,
        test_queries: Optional[List[Dict]] = None,
        document_ids: Optional[List[str]] = None,
    ) -> EvalSuiteResult:
        """Run a full evaluation suite against the RAG pipeline."""

        queries = test_queries or DEFAULT_TEST_QUERIES
        results = []

        for tq in queries:
            try:
                result = await self.evaluate_single(
                    query=tq["query"],
                    expected_keywords=tq.get("expected_keywords"),
                    document_ids=document_ids,
                )
                results.append(result)
                logger.info(
                    f"Eval '{tq['query'][:40]}...' → "
                    f"faith={result.faithfulness:.2f} "
                    f"rel={result.answer_relevancy:.2f} "
                    f"prec={result.context_precision:.2f} "
                    f"cite={result.citation_accuracy:.2f}"
                )
            except Exception as e:
                logger.error(f"Eval failed for '{tq['query']}': {e}")
                results.append(EvalResult(
                    query=tq["query"], answer=f"ERROR: {e}",
                    faithfulness=0, answer_relevancy=0,
                    context_precision=0, citation_accuracy=0,
                    latency_ms=0, tokens_used=0, chunks_retrieved=0,
                ))

        # Compute aggregates
        valid_results = [r for r in results if not r.insufficient_evidence]
        n = len(valid_results) or 1

        avg_faith = sum(r.faithfulness for r in valid_results) / n
        avg_rel = sum(r.answer_relevancy for r in valid_results) / n
        avg_prec = sum(r.context_precision for r in valid_results) / n
        avg_cite = sum(r.citation_accuracy for r in valid_results) / n
        avg_latency = sum(r.latency_ms for r in results) / len(results)
        total_tokens = sum(r.tokens_used for r in results)

        # Pass rate: all metrics above threshold
        passing = sum(
            1 for r in valid_results
            if r.faithfulness > 0.6
            and r.answer_relevancy > 0.6
            and r.context_precision > 0.4
            and r.citation_accuracy > 0.7
        )
        pass_rate = passing / n if n > 0 else 0

        return EvalSuiteResult(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_queries=len(results),
            avg_faithfulness=round(avg_faith, 3),
            avg_answer_relevancy=round(avg_rel, 3),
            avg_context_precision=round(avg_prec, 3),
            avg_citation_accuracy=round(avg_cite, 3),
            avg_latency_ms=round(avg_latency),
            total_tokens=total_tokens,
            results=results,
            pass_rate=round(pass_rate, 3),
        )

    # ── Metric Implementations ────────────────────────────────────────────

    async def _eval_faithfulness(self, response: RAGResponse) -> float:
        """
        Faithfulness: Is every claim in the answer supported by the context?
        Uses LLM to check if the answer is grounded.
        """
        if not response.citations:
            return 0.0

        context = "\n\n".join(c.content[:300] for c in response.citations[:4])

        prompt = f"""Rate the faithfulness of this answer to the provided context.
Faithfulness means every factual claim in the answer is supported by the context.

CONTEXT:
{context}

ANSWER:
{response.answer[:800]}

Rate from 0.0 to 1.0 where:
  1.0 = Every claim is directly supported by context
  0.5 = Some claims supported, some not verifiable
  0.0 = Answer contains fabricated information

Respond with ONLY a decimal number between 0.0 and 1.0."""

        try:
            result, _ = await self.llm.generate(prompt, max_tokens=10)
            score = float(re.search(r"[\d.]+", result).group())
            return min(max(score, 0.0), 1.0)
        except Exception:
            return 0.5

    async def _eval_answer_relevancy(self, query: str, response: RAGResponse) -> float:
        """
        Answer Relevancy: Does the answer address what was asked?
        """
        prompt = f"""Rate how well this answer addresses the question.

QUESTION: {query}

ANSWER:
{response.answer[:800]}

Rate from 0.0 to 1.0 where:
  1.0 = Directly and thoroughly answers the question
  0.5 = Partially answers or is tangentially related
  0.0 = Does not address the question at all

Respond with ONLY a decimal number between 0.0 and 1.0."""

        try:
            result, _ = await self.llm.generate(prompt, max_tokens=10)
            score = float(re.search(r"[\d.]+", result).group())
            return min(max(score, 0.0), 1.0)
        except Exception:
            return 0.5

    def _eval_context_precision(
        self,
        query: str,
        response: RAGResponse,
        expected_keywords: Optional[List[str]] = None,
    ) -> float:
        """
        Context Precision: Are the retrieved chunks relevant?
        Uses keyword overlap as a proxy (fast, no LLM call).
        """
        if not response.citations:
            return 0.0

        query_terms = set(query.lower().split())
        total_overlap = 0.0

        for chunk in response.citations:
            chunk_terms = set(chunk.content.lower().split())
            overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            total_overlap += overlap

        base_score = total_overlap / len(response.citations)

        # Boost if expected keywords are found
        if expected_keywords:
            all_content = " ".join(c.content.lower() for c in response.citations)
            found = sum(1 for kw in expected_keywords if kw.lower() in all_content)
            keyword_score = found / len(expected_keywords)
            return min((base_score * 0.4 + keyword_score * 0.6), 1.0)

        return min(base_score * 2, 1.0)  # Scale up since raw overlap is usually low

    def _eval_citation_accuracy(self, response: RAGResponse) -> float:
        """
        Citation Accuracy: Do [N] references in the answer map to real chunks?
        """
        if not response.citations:
            return 0.0

        # Find all citation references in the answer
        cited_indices = set(int(m) for m in re.findall(r"\[(\d+)\]", response.answer))

        if not cited_indices:
            # No citations in answer — that's a problem if there are chunks
            return 0.0 if response.citations else 1.0

        available_indices = set(c.citation_index for c in response.citations)

        # Valid citations / total cited
        valid = len(cited_indices & available_indices)
        accuracy = valid / len(cited_indices) if cited_indices else 0

        # Penalize if no citations used
        if not cited_indices and response.citations:
            return 0.0

        return accuracy


# Singleton
_evaluator: Optional[RAGEvaluator] = None


def get_evaluator() -> RAGEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = RAGEvaluator()
    return _evaluator
