"""
Agent State — defines the shared state that flows through the LangGraph nodes.

This is the "memory" of a single agent invocation. LangGraph passes this state
object through every node, and each node can read/write to it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentAction(str, Enum):
    """Actions the router can dispatch to."""
    RETRIEVE = "retrieve"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    EXTRACT = "extract"
    CLARIFY = "clarify"


class QueryComplexity(str, Enum):
    SIMPLE = "simple"          # Single retrieval + answer
    MODERATE = "moderate"      # May need re-query
    COMPLEX = "complex"        # Multi-step, comparison, extraction


@dataclass
class RetrievedChunk:
    """A single chunk retrieved from the vector store."""
    chunk_id: str
    document_id: str
    document_filename: str
    content: str
    page_number: Optional[int]
    relevance_score: float
    citation_index: int = 0


@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""
    role: str           # "user" | "assistant"
    content: str
    citations: List[RetrievedChunk] = field(default_factory=list)


@dataclass
class AgentState:
    """
    The complete state passed through every LangGraph node.

    LangGraph requires state to be the single source of truth.
    Every node reads what it needs and writes its outputs here.
    """

    # ── Input ──────────────────────────────────────────────────────────
    original_query: str = ""
    mode: str = "qa"                              # "qa" | "summarize"
    document_ids: Optional[List[str]] = None      # scope to specific docs

    # ── Conversation Memory ────────────────────────────────────────────
    conversation_history: List[ConversationTurn] = field(default_factory=list)

    # ── Router Decision ────────────────────────────────────────────────
    action: AgentAction = AgentAction.RETRIEVE
    complexity: QueryComplexity = QueryComplexity.SIMPLE
    router_reasoning: str = ""

    # ── Retrieval ──────────────────────────────────────────────────────
    current_query: str = ""                       # may differ from original after reformulation
    retrieved_chunks: List[RetrievedChunk] = field(default_factory=list)
    retrieval_sufficient: bool = False
    retrieval_attempts: int = 0
    max_retrieval_attempts: int = 3

    # ── Generation ─────────────────────────────────────────────────────
    generated_answer: str = ""
    tokens_used: int = 0

    # ── Validation ─────────────────────────────────────────────────────
    validation_passed: bool = False
    validation_issues: List[str] = field(default_factory=list)
    validation_attempts: int = 0
    max_validation_attempts: int = 2

    # ── Final Output ───────────────────────────────────────────────────
    final_answer: str = ""
    citations: List[RetrievedChunk] = field(default_factory=list)
    confidence: float = 0.0
    insufficient_evidence: bool = False

    # ── Metrics ────────────────────────────────────────────────────────
    start_time: float = 0.0
    latency_ms: int = 0
    total_tokens: int = 0

    # ── Error Handling ─────────────────────────────────────────────────
    error: Optional[str] = None
