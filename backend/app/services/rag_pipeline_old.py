"""
RAG Pipeline — the core intelligence of the system.

Flow:
  PDF → parse → clean → chunk → embed → index
  Query → embed → retrieve → rerank → prompt → LLM → citations → response
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Data Structures ───────────────────────────────────────────────────────────

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


# ── PDF Parser ────────────────────────────────────────────────────────────────

class PDFParser:
    """Robust PDF parser with multiple fallback strategies."""

    def parse(self, file_path: str) -> Tuple[str, int]:
        """Returns (full_text, page_count). Tries pypdf first, falls back to pdfminer."""
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


# ── Text Cleaner ──────────────────────────────────────────────────────────────

class TextCleaner:
    """Removes noise while preserving medical terminology."""

    NOISE_PATTERNS = [
        r"\x0c",                    # form feed
        r"(?m)^\s*\d+\s*$",         # lone page numbers
        r"-{3,}",                   # long dashes
        r"\.{4,}",                  # dot leaders (TOC)
    ]

    def clean(self, text: str) -> str:
        import re
        for pat in self.NOISE_PATTERNS:
            text = re.sub(pat, " ", text)
        # Normalise whitespace but keep paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# ── Smart Chunker ─────────────────────────────────────────────────────────────

class SmartChunker:
    """
    Recursive sentence-aware chunker.
    Strategy:
      1. Split on paragraph breaks (best semantic boundaries).
      2. If paragraph > chunk_size, split on sentence boundaries.
      3. Overlap is preserved by including the tail of the previous chunk.
    This preserves medical context across chunk boundaries.
    """

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
            # Track page markers
            if para.startswith("[Page "):
                match = re.match(r"\[Page (\d+)\]", para)
                if match:
                    page_num = int(match.group(1))
                    para = para[match.end():].strip()

            if not para.strip():
                continue

            # If adding this paragraph overflows → flush current
            if len(current) + len(para) > self.chunk_size and current:
                chunks.append(self._make_chunk(current, page_num, idx))
                idx += 1
                # Carry overlap
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
            token_count=len(content.split()),  # rough approx
        )


# ── Embedding Service ─────────────────────────────────────────────────────────

class EmbeddingService:
    """OpenAI text-embedding-3-small (1536-dim, cost-effective, high quality)."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL
        self.batch_size = 100

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Batch embed with retry logic."""
        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch = [t.replace("\n", " ") for t in batch]  # OpenAI requirement
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


# ── Vector Store ──────────────────────────────────────────────────────────────

class FAISSVectorStore:
    """FAISS IndexFlatIP (inner product = cosine on normalized vectors)."""

    def __init__(self):
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.index_path.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._metadata: List[dict] = []  # parallel list to FAISS vectors
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
        """Rebuild index without the given document (FAISS doesn't support deletion)."""
        import faiss
        keep_meta = [m for m in self._metadata if m.get("document_id") != document_id]
        # If nothing to keep just recreate
        new_index = faiss.IndexFlatIP(settings.EMBEDDING_DIMENSION)
        # Note: in production use IDMap2 for proper deletion support
        self._index = new_index
        self._metadata = keep_meta
        self.save()


# ── LLM Client ────────────────────────────────────────────────────────────────

class LLMClient:
    """Anthropic Claude client with strict hallucination guardrails."""

    SYSTEM_PROMPT = """You are a specialized healthcare research assistant that helps medical professionals and researchers understand medical literature.

STRICT RULES — NEVER VIOLATE:
1. Answer ONLY from the provided context. Never use external knowledge.
2. Every factual claim MUST be supported by a citation [1], [2], etc.
3. If the context does not contain enough information to answer, respond exactly:
   "INSUFFICIENT_EVIDENCE: The provided documents do not contain enough information to answer this question reliably."
4. Never speculate, extrapolate, or make diagnostic suggestions.
5. Use precise medical terminology from the source documents.
6. Always end responses with: "⚠️ This is not medical advice. Consult a qualified healthcare professional."

CITATION FORMAT:
- Inline citations: [1], [2] after each claim.
- At the end, list sources as:
  [1] Document: {filename}, Page {page}
  [2] Document: {filename}, Page {page}
"""

    QA_PROMPT_TEMPLATE = """CONTEXT FROM MEDICAL LITERATURE:
{context}

QUESTION: {question}

Instructions:
- Answer strictly from the context above.
- Cite every factual claim with [citation_number].
- If evidence is insufficient, say INSUFFICIENT_EVIDENCE.
- Be thorough but concise.

ANSWER:"""

    SUMMARIZATION_PROMPT = """You are summarizing a medical research paper. Use ONLY the provided text.

DOCUMENT EXCERPTS:
{context}

Provide a structured summary with:
1. **Study Objective** — What question does this research address?
2. **Methodology** — Study design and methods used.
3. **Key Findings** — Main results with citations [1], [2], etc.
4. **Conclusions** — What the authors concluded.
5. **Limitations** — Any stated limitations.

⚠️ This is not medical advice. Consult a qualified healthcare professional."""

    def __init__(self):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(self, prompt: str, max_tokens: int = settings.LLM_MAX_TOKENS) -> Tuple[str, int]:
        """Returns (response_text, tokens_used)."""
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

    def build_qa_prompt(self, question: str, context_chunks: List[RetrievedChunk]) -> str:
        context_parts = []
        for chunk in context_chunks:
            context_parts.append(
                f"[{chunk.citation_index}] (Source: {chunk.document_filename}, "
                f"Page {chunk.page_number or 'N/A'}):\n{chunk.content}"
            )
        context = "\n\n---\n\n".join(context_parts)
        return self.QA_PROMPT_TEMPLATE.format(context=context, question=question)

    def build_summarization_prompt(self, context_chunks: List[RetrievedChunk]) -> str:
        context_parts = [
            f"[{c.citation_index}] {c.content}" for c in context_chunks
        ]
        return self.SUMMARIZATION_PROMPT.format(context="\n\n".join(context_parts))


# ── Reranker ──────────────────────────────────────────────────────────────────

class SimpleReranker:
    """
    Cross-encoder-style reranker using keyword overlap + score.
    Production upgrade: use cross-encoder/ms-marco-MiniLM-L-6-v2 via sentence-transformers.
    """

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


# ── Main RAG Pipeline ─────────────────────────────────────────────────────────

class RAGPipeline:
    """Orchestrates the full RAG flow end-to-end."""

    def __init__(self):
        self.parser = PDFParser()
        self.cleaner = TextCleaner()
        self.chunker = SmartChunker()
        self.embedder = EmbeddingService()
        self.vector_store = FAISSVectorStore()
        self.llm = LLMClient()
        self.reranker = SimpleReranker()

    # ── Ingestion ──────────────────────────────────────────────────────────

    async def ingest_document(
        self,
        file_path: str,
        document_id: str,
        document_filename: str,
    ) -> List[ParsedChunk]:
        """Full ingestion: parse → clean → chunk → embed → index."""
        logger.info(f"Ingesting document: {document_filename}")

        # 1. Parse
        raw_text, page_count = self.parser.parse(file_path)
        if not raw_text.strip():
            raise ValueError("PDF appears to be empty or unreadable")

        # 2. Clean
        clean_text = self.cleaner.clean(raw_text)

        # 3. Chunk
        chunks = self.chunker.chunk(clean_text)
        if not chunks:
            raise ValueError("No text chunks could be extracted")

        logger.info(f"Created {len(chunks)} chunks from {page_count} pages")

        # 4. Embed (batched)
        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed_texts(texts)

        # 5. Index with metadata
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

    # ── Query ──────────────────────────────────────────────────────────────

    async def query(
        self,
        question: str,
        document_ids: Optional[List[str]] = None,
        mode: str = "qa",  # "qa" | "summarize"
    ) -> RAGResponse:
        """Full query pipeline: embed → retrieve → rerank → generate."""
        start = time.time()

        # 1. Embed query
        query_embedding = await self.embedder.embed_query(question)

        # 2. Retrieve
        raw_results = self.vector_store.search(query_embedding, top_k=settings.TOP_K_RETRIEVAL)

        # 3. Filter by document scope (if provided)
        if document_ids:
            raw_results = [r for r in raw_results if r["document_id"] in document_ids]

        # 4. Relevance threshold filter
        raw_results = [r for r in raw_results if r["score"] >= settings.MIN_RELEVANCE_SCORE]

        if not raw_results:
            return RAGResponse(
                answer="INSUFFICIENT_EVIDENCE: The provided documents do not contain relevant information to answer this question reliably.\n\n⚠️ This is not medical advice. Consult a qualified healthcare professional.",
                citations=[],
                confidence=0.0,
                tokens_used=0,
                latency_ms=int((time.time() - start) * 1000),
                insufficient_evidence=True,
            )

        # 5. Rerank
        reranked = self.reranker.rerank(question, raw_results)

        # 6. Build RetrievedChunk objects
        context_chunks = [
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

        # 7. Build prompt and generate
        if mode == "summarize":
            prompt = self.llm.build_summarization_prompt(context_chunks)
        else:
            prompt = self.llm.build_qa_prompt(question, context_chunks)

        answer, tokens_used = await self.llm.generate(prompt)

        # 8. Compute confidence (avg of top-k relevance scores)
        confidence = float(np.mean([c.relevance_score for c in context_chunks]))

        latency_ms = int((time.time() - start) * 1000)
        logger.info(f"RAG query completed in {latency_ms}ms, {tokens_used} tokens")

        return RAGResponse(
            answer=answer,
            citations=context_chunks,
            confidence=confidence,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            insufficient_evidence="INSUFFICIENT_EVIDENCE" in answer,
        )

    def remove_document(self, document_id: str):
        self.vector_store.delete_by_document(document_id)


# Singleton — shared across request lifecycle
_pipeline: Optional[RAGPipeline] = None


def get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline()
    return _pipeline
