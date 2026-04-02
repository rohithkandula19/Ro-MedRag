"""
RAG Pipeline — refactored to use the LangGraph agent.

The original pipeline classes (PDFParser, TextCleaner, SmartChunker,
EmbeddingService, FAISSVectorStore, SimpleReranker) remain unchanged.

The query path now flows through the MedRAGAgent instead of a simple
embed → retrieve → rerank → generate chain.

Backward compatibility is fully preserved:
  - get_pipeline() still returns a RAGPipeline
  - RAGPipeline.query() still returns a RAGResponse
  - RAGPipeline.ingest_document() is unchanged
  - All dataclasses remain the same
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

# Agent imports
from app.services.agent.state import (
    AgentState,
    ConversationTurn,
    RetrievedChunk as AgentRetrievedChunk,
)
from app.services.agent.graph import MedRAGAgent
from app.services.agent.tools import RetrievalTool

logger = get_logger(__name__)


# ── Data Structures (unchanged — backward compatible) ─────────────────────────

@dataclass
class ParsedChunk:
    content: str
    page_number: int
    chunk_index: int
    section_title: Optional[str] = None
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_filename: str
    content: str
    page_number: Optional[int]
    relevance_score: float
    citation_index: int = 0


@dataclass
class RAGResponse:
    answer: str
    citations: List[RetrievedChunk]
    confidence: float
    tokens_used: int
    latency_ms: int
    insufficient_evidence: bool = False


# ── PDF Parser (unchanged) ────────────────────────────────────────────────────

class PDFParser:
    """Robust PDF parser with multiple fallback strategies."""

    def parse(self, file_path: str) -> Tuple[str, int]:
        try:
            return self._parse_pypdf(file_path)
        except Exception as e:
            logger.warning(f"pypdf failed ({e}), trying pdfminer")
            try:
                return self._parse_pdfminer(file_path)
            except Exception as e2:
                raise ValueError(f"PDF parsing failed: {e2}") from e2

    def _parse_pypdf(self, file_path: str) -> Tuple[str, int]:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[Page {i+1}]\n{text}")
        return "\n\n".join(pages), len(reader.pages)

    def _parse_pdfminer(self, file_path: str) -> Tuple[str, int]:
        from pdfminer.high_level import extract_text, extract_pages
        text = extract_text(file_path)
        page_count = sum(1 for _ in extract_pages(file_path))
        return text, page_count


# ── Text Cleaner (unchanged) ─────────────────────────────────────────────────

class TextCleaner:
    NOISE_PATTERNS = [
        r"\x0c",
        r"(?m)^\s*\d+\s*$",
        r"-{3,}",
        r"\.{4,}",
    ]

    def clean(self, text: str) -> str:
        import re
        for pat in self.NOISE_PATTERNS:
            text = re.sub(pat, " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# ── Smart Chunker (unchanged) ────────────────────────────────────────────────

class SmartChunker:
    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> List[ParsedChunk]:
        import re
        chunks: List[ParsedChunk] = []
        paragraphs = re.split(r"\n\n+", text)
        current = ""
        page_num = 1
        idx = 0

        for para in paragraphs:
            if para.startswith("[Page "):
                match = re.match(r"\[Page (\d+)\]", para)
                if match:
                    page_num = int(match.group(1))
                    para = para[match.end():].strip()

            if not para.strip():
                continue

            if len(current) + len(para) > self.chunk_size and current:
                chunks.append(self._make_chunk(current, page_num, idx))
                idx += 1
                words = current.split()
                overlap_words = words[-self.chunk_overlap:] if len(words) > self.chunk_overlap else words
                current = " ".join(overlap_words) + " " + para
            else:
                current = (current + "\n\n" + para).strip() if current else para

        if current.strip():
            chunks.append(self._make_chunk(current, page_num, idx))

        return chunks

    def _make_chunk(self, content: str, page: int, idx: int) -> ParsedChunk:
        return ParsedChunk(
            content=content.strip(),
            page_number=page,
            chunk_index=idx,
            token_count=len(content.split()),
        )


# ── Embedding Service (unchanged) ────────────────────────────────────────────

class EmbeddingService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.batch_size = 100

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch = [t.replace("\n", " ") for t in batch]
            for attempt in range(3):
                try:
                    resp = await self.client.embeddings.create(
                        model=self.model, input=batch
                    )
                    all_embeddings.extend([e.embedding for e in resp.data])
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)
                    logger.warning(f"Embedding retry {attempt+1}: {e}")
        return all_embeddings

    async def embed_query(self, query: str) -> List[float]:
        result = await self.embed_texts([query])
        return result[0]


# ── Vector Store (unchanged) ──────────────────────────────────────────────────

class FAISSVectorStore:
    def __init__(self):
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.index_path.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._metadata: List[dict] = []
        self._load_or_create()

    def _load_or_create(self):
        import faiss, pickle
        idx_file = self.index_path / "index.faiss"
        meta_file = self.index_path / "metadata.pkl"
        if idx_file.exists() and meta_file.exists():
            self._index = faiss.read_index(str(idx_file))
            with open(meta_file, "rb") as f:
                self._metadata = pickle.load(f)
            logger.info(f"FAISS loaded: {self._index.ntotal} vectors")
        else:
            self._index = faiss.IndexFlatIP(settings.EMBEDDING_DIMENSION)
            self._metadata = []
            logger.info("FAISS index created (fresh)")

    def save(self):
        import faiss, pickle
        faiss.write_index(self._index, str(self.index_path / "index.faiss"))
        with open(self.index_path / "metadata.pkl", "wb") as f:
            pickle.dump(self._metadata, f)

    def add(self, embeddings: List[List[float]], metadata: List[dict]):
        import faiss
        vecs = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vecs)
        self._index.add(vecs)
        self._metadata.extend(metadata)
        self.save()

    def search(self, query_embedding: List[float], top_k: int = settings.TOP_K_RETRIEVAL):
        import faiss
        if self._index.ntotal == 0:
            return []
        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)
        scores, indices = self._index.search(vec, min(top_k, self._index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self._metadata[idx].copy()
            meta["score"] = float(score)
            results.append(meta)
        return results

    def delete_by_document(self, document_id: str):
        import faiss
        keep_meta = [m for m in self._metadata if m.get("document_id") != document_id]
        new_index = faiss.IndexFlatIP(settings.EMBEDDING_DIMENSION)
        self._index = new_index
        self._metadata = keep_meta
        self.save()


# ── LLM Client (unchanged) ──────────────────────────────────────────────────

class LLMClient:
    """Anthropic Claude client — now used by both direct calls and agent nodes."""

    SYSTEM_PROMPT = """You are a specialized healthcare research assistant that helps medical professionals and researchers understand medical literature.

STRICT RULES — NEVER VIOLATE:
1. Answer ONLY from the provided context. Never use external knowledge.
2. Every factual claim MUST be supported by a citation [1], [2], etc.
3. If the context does not contain enough information to answer, respond exactly:
   "INSUFFICIENT_EVIDENCE: The provided documents do not contain enough information to answer this question reliably."
4. Never speculate, extrapolate, or make diagnostic suggestions.
5. Use precise medical terminology from the source documents.
6. Always end responses with: "⚠️ This is not medical advice. Consult a qualified healthcare professional."
"""

    def __init__(self):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(self, prompt: str, max_tokens: int = settings.LLM_MAX_TOKENS) -> Tuple[str, int]:
        response = await self.client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            temperature=settings.LLM_TEMPERATURE,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return text, tokens


# ── Reranker (unchanged) ─────────────────────────────────────────────────────

class SimpleReranker:
    def rerank(
        self,
        query: str,
        chunks: List[dict],
        top_k: int = settings.TOP_K_RERANK,
    ) -> List[dict]:
        query_terms = set(query.lower().split())
        for chunk in chunks:
            content_terms = set(chunk["content"].lower().split())
            overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
            chunk["rerank_score"] = chunk["score"] * 0.7 + overlap * 0.3
        reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]


# ── Conversation Memory Manager ─────────────────────────────────────────────

class ConversationMemory:
    """
    Manages conversation history per chat session.
    Stores recent turns for multi-turn context.
    """

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._sessions: dict[str, List[ConversationTurn]] = {}

    def get_history(self, session_id: str) -> List[ConversationTurn]:
        return self._sessions.get(session_id, [])

    def add_turn(self, session_id: str, role: str, content: str):
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(
            ConversationTurn(role=role, content=content)
        )
        # Trim to max turns
        if len(self._sessions[session_id]) > self.max_turns:
            self._sessions[session_id] = self._sessions[session_id][-self.max_turns:]

    def clear_session(self, session_id: str):
        self._sessions.pop(session_id, None)


# ── Main RAG Pipeline (refactored with Agent) ────────────────────────────────

class RAGPipeline:
    """
    Orchestrates the full RAG flow.

    WHAT CHANGED:
      - query() now uses MedRAGAgent instead of direct embed→retrieve→generate
      - Conversation memory is maintained across turns
      - Agent decides when to re-query, compare, extract, or clarify

    WHAT STAYED THE SAME:
      - ingest_document() is unchanged
      - All data structures are backward compatible
      - The API surface is identical
    """

    def __init__(self):
        # ── Existing components (unchanged) ────────────────────────────
        self.parser = PDFParser()
        self.cleaner = TextCleaner()
        self.chunker = SmartChunker()
        self.embedder = EmbeddingService()
        self.vector_store = FAISSVectorStore()
        self.llm = LLMClient()
        self.reranker = SimpleReranker()

        # ── New: Agent components ──────────────────────────────────────
        self.retrieval_tool = RetrievalTool(
            embedder=self.embedder,
            vector_store=self.vector_store,
            reranker=self.reranker,
        )
        self.agent = MedRAGAgent(
            llm_client=self.llm,
            retrieval_tool=self.retrieval_tool,
            reranker=self.reranker,
        )
        self.memory = ConversationMemory()

    # ── Ingestion (unchanged) ──────────────────────────────────────────

    async def ingest_document(
        self,
        file_path: str,
        document_id: str,
        document_filename: str,
    ) -> List[ParsedChunk]:
        logger.info(f"Ingesting document: {document_filename}")

        raw_text, page_count = self.parser.parse(file_path)
        if not raw_text.strip():
            raise ValueError("PDF appears to be empty or unreadable")

        clean_text = self.cleaner.clean(raw_text)
        chunks = self.chunker.chunk(clean_text)
        if not chunks:
            raise ValueError("No text chunks could be extracted")

        logger.info(f"Created {len(chunks)} chunks from {page_count} pages")

        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed_texts(texts)

        metadata = [
            {
                "chunk_id": f"{document_id}_{c.chunk_index}",
                "document_id": document_id,
                "document_filename": document_filename,
                "content": c.content,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]
        self.vector_store.add(embeddings, metadata)
        logger.info(f"Indexed {len(chunks)} chunks for document {document_id}")

        return chunks

    # ── Query (REFACTORED — now uses agent) ────────────────────────────

    async def query(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
        mode: str = "qa",
        session_id: Optional[str] = None,
    ) -> RAGResponse:
        """
        Full query pipeline — now powered by the LangGraph agent.

        The agent:
          1. Routes the query (retrieve / summarize / compare / extract / clarify)
          2. Retrieves with automatic re-query if needed
          3. Generates an answer with citations
          4. Self-validates against sources
          5. Returns final response

        Args:
            question:     The user's query
            document_ids: Optional scope to specific documents
            mode:         "qa" or "summarize"
            session_id:   For conversation memory across turns
        """

        # Build agent state with conversation history
        conversation_history = []
        if session_id:
            conversation_history = self.memory.get_history(session_id)

        state = AgentState(
            original_query=question.strip(),
            mode=mode,
            document_ids=document_ids,
            conversation_history=conversation_history,
        )

        # Run the agent
        final_state = await self.agent.run(state)

        # Update conversation memory
        if session_id:
            self.memory.add_turn(session_id, "user", question.strip())
            self.memory.add_turn(session_id, "assistant", final_state.final_answer)

        # Convert agent citations to backward-compatible format
        citations = [
            RetrievedChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_filename=c.document_filename,
                content=c.content,
                page_number=c.page_number,
                relevance_score=c.relevance_score,
                citation_index=c.citation_index,
            )
            for c in final_state.citations
        ]

        return RAGResponse(
            answer=final_state.final_answer,
            citations=citations,
            confidence=final_state.confidence,
            tokens_used=final_state.total_tokens,
            latency_ms=final_state.latency_ms,
            insufficient_evidence=final_state.insufficient_evidence,
        )

    def remove_document(self, document_id: str):
        self.vector_store.delete_by_document(document_id)

    def clear_session_memory(self, session_id: str):
        """Clear conversation memory for a session."""
        self.memory.clear_session(session_id)


# Singleton
_pipeline: Optional[RAGPipeline] = None


def get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
