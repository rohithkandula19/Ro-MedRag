"""
Agent Nodes — each function is a node in the LangGraph workflow.

Each node:
  - Receives the full AgentState
  - Performs one step of reasoning or action
  - Returns a dict of state updates (LangGraph merges them)

Node naming convention: verb_noun (e.g., route_query, retrieve_context)
"""

import time
from typing import Any, Dict

import numpy as np

from app.core.config import settings
from app.core.logging import get_logger
from app.services.agent.state import (
    AgentAction,
    AgentState,
    ConversationTurn,
    QueryComplexity,
    RetrievedChunk,
)
from app.services.agent.tools import (
    AnswerValidator,
    ComparisonTool,
    DataExtractionTool,
    QueryReformulationTool,
    RetrievalTool,
    SufficiencyEvaluator,
)

logger = get_logger(__name__)


# ── Node: Route Query ─────────────────────────────────────────────────────────

async def route_query(state: AgentState, llm_client) -> Dict[str, Any]:
    """
    The brain of the agent. Analyzes the query and decides:
      - What action to take (retrieve, summarize, compare, extract, clarify)
      - Query complexity (simple, moderate, complex)
      - Whether to use conversation history for context

    This node uses the LLM to make routing decisions.
    """

    # Build conversation context for the router
    conv_context = ""
    if state.conversation_history:
        recent = state.conversation_history[-4:]  # Last 4 turns
        conv_context = "\n".join(
            f"{t.role.upper()}: {t.content[:200]}" for t in recent
        )

    prompt = f"""You are a medical research query router. Analyze the user's query and decide
the best action to take.

{f'CONVERSATION HISTORY:{chr(10)}{conv_context}{chr(10)}' if conv_context else ''}
USER QUERY: {state.original_query}

Decide the following:
1. ACTION — one of: retrieve, summarize, compare, extract, clarify
   - retrieve: Standard Q&A, find relevant information
   - summarize: User wants a summary of documents
   - compare: User is comparing treatments, studies, or approaches
   - extract: User wants specific data points extracted (dosages, criteria, stats)
   - clarify: Query is too vague or ambiguous to search effectively

2. COMPLEXITY — one of: simple, moderate, complex
   - simple: Single-step retrieval and answer
   - moderate: May need query refinement
   - complex: Multi-document, comparative, or multi-step reasoning

3. SEARCH_QUERY — the optimized search query to use for retrieval
   (rewrite the user's query into an effective search query)

Respond in this EXACT format:
ACTION: <action>
COMPLEXITY: <complexity>
SEARCH_QUERY: <search_query>
REASONING: <brief explanation>"""

    response, tokens = await llm_client.generate(prompt, max_tokens=200)

    # Parse response
    action = AgentAction.RETRIEVE
    complexity = QueryComplexity.SIMPLE
    search_query = state.original_query
    reasoning = ""

    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("ACTION:"):
            action_str = line.split(":", 1)[1].strip().lower()
            try:
                action = AgentAction(action_str)
            except ValueError:
                action = AgentAction.RETRIEVE
        elif line.startswith("COMPLEXITY:"):
            complexity_str = line.split(":", 1)[1].strip().lower()
            try:
                complexity = QueryComplexity(complexity_str)
            except ValueError:
                complexity = QueryComplexity.SIMPLE
        elif line.startswith("SEARCH_QUERY:"):
            search_query = line.split(":", 1)[1].strip()
        elif line.startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    # Override: if mode is explicitly "summarize", force that action
    if state.mode == "summarize":
        action = AgentAction.SUMMARIZE

    logger.info(f"Router → action={action.value}, complexity={complexity.value}, query='{search_query}'")

    return {
        "action": action,
        "complexity": complexity,
        "current_query": search_query,
        "router_reasoning": reasoning,
        "total_tokens": state.total_tokens + tokens,
    }


# ── Node: Retrieve Context ───────────────────────────────────────────────────

async def retrieve_context(state: AgentState, retrieval_tool: RetrievalTool) -> Dict[str, Any]:
    """
    Retrieves relevant document chunks from the vector store.
    Supports iterative retrieval (re-query with reformulated query).
    """

    chunks = await retrieval_tool.retrieve(
        query=state.current_query,
        document_ids=state.document_ids,
    )

    return {
        "retrieved_chunks": chunks,
        "retrieval_attempts": state.retrieval_attempts + 1,
    }


# ── Node: Evaluate Sufficiency ───────────────────────────────────────────────

async def evaluate_sufficiency(state: AgentState, evaluator: SufficiencyEvaluator) -> Dict[str, Any]:
    """
    Checks if retrieval results are good enough to generate an answer.
    If not, the graph will loop back to re-query.
    """

    is_sufficient = evaluator.evaluate(
        query=state.current_query,
        chunks=state.retrieved_chunks,
    )

    logger.info(
        f"Sufficiency check: {'PASS' if is_sufficient else 'FAIL'} "
        f"(attempt {state.retrieval_attempts}/{state.max_retrieval_attempts}, "
        f"{len(state.retrieved_chunks)} chunks)"
    )

    return {"retrieval_sufficient": is_sufficient}


# ── Node: Reformulate Query ──────────────────────────────────────────────────

async def reformulate_query(
    state: AgentState, reformulation_tool: QueryReformulationTool
) -> Dict[str, Any]:
    """
    When retrieval is insufficient, generate a better search query.
    Uses the LLM to analyze what went wrong and try different terms.
    """

    conv_context = ""
    if state.conversation_history:
        conv_context = "\n".join(
            f"{t.role}: {t.content[:100]}" for t in state.conversation_history[-2:]
        )

    new_query = await reformulation_tool.reformulate(
        original_query=state.original_query,
        retrieved_chunks=state.retrieved_chunks,
        attempt=state.retrieval_attempts,
        conversation_context=conv_context,
    )

    logger.info(f"Query reformulated: '{state.current_query}' → '{new_query}'")

    return {"current_query": new_query}


# ── Node: Compare Documents ──────────────────────────────────────────────────

async def compare_documents(
    state: AgentState,
    comparison_tool: ComparisonTool,
    llm_client,
) -> Dict[str, Any]:
    """
    For comparison queries, extract subjects and retrieve for each.
    """

    # Use LLM to identify comparison subjects
    prompt = f"""From this query, identify the 2-4 distinct subjects being compared.

QUERY: {state.original_query}

List each subject on a separate line, nothing else.
Example:
metformin
insulin
sulfonylureas"""

    subjects_text, tokens = await llm_client.generate(prompt, max_tokens=100)
    subjects = [s.strip() for s in subjects_text.strip().split("\n") if s.strip()]

    if len(subjects) < 2:
        # Fallback: treat as regular retrieval
        subjects = [state.original_query]

    chunks = await comparison_tool.compare(
        query=state.original_query,
        subjects=subjects,
        document_ids=state.document_ids,
    )

    return {
        "retrieved_chunks": chunks,
        "retrieval_sufficient": len(chunks) > 0,
        "total_tokens": state.total_tokens + tokens,
    }


# ── Node: Generate Answer ───────────────────────────────────────────────────

async def generate_answer(state: AgentState, llm_client) -> Dict[str, Any]:
    """
    Uses the LLM to generate an answer from retrieved context.
    Includes conversation history for multi-turn coherence.
    """

    # Handle no results
    if not state.retrieved_chunks:
        return {
            "generated_answer": (
                "INSUFFICIENT_EVIDENCE: The provided documents do not contain "
                "enough information to answer this question reliably.\n\n"
                "⚠️ This is not medical advice. Consult a qualified healthcare professional."
            ),
            "insufficient_evidence": True,
            "tokens_used": 0,
        }

    # Build context from chunks
    context_parts = []
    for chunk in state.retrieved_chunks:
        context_parts.append(
            f"[{chunk.citation_index}] (Source: {chunk.document_filename}, "
            f"Page {chunk.page_number or 'N/A'}):\n{chunk.content}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # Build conversation history for multi-turn
    history_section = ""
    if state.conversation_history:
        recent = state.conversation_history[-6:]
        history_parts = []
        for turn in recent:
            history_parts.append(f"{turn.role.upper()}: {turn.content[:300]}")
        history_section = f"""
CONVERSATION HISTORY (for context continuity):
{chr(10).join(history_parts)}

"""

    # Select prompt based on action
    if state.action == AgentAction.SUMMARIZE:
        prompt = _build_summarize_prompt(context, state.original_query, history_section)
    elif state.action == AgentAction.EXTRACT:
        prompt = _build_extract_prompt(context, state.original_query, history_section)
    elif state.action == AgentAction.COMPARE:
        prompt = _build_compare_prompt(context, state.original_query, history_section)
    else:
        prompt = _build_qa_prompt(context, state.original_query, history_section)

    answer, tokens = await llm_client.generate(prompt)

    return {
        "generated_answer": answer,
        "tokens_used": tokens,
        "total_tokens": state.total_tokens + tokens,
    }


# ── Node: Validate Answer ───────────────────────────────────────────────────

async def validate_answer(state: AgentState, validator: AnswerValidator) -> Dict[str, Any]:
    """
    Self-correction: verify the answer is grounded in retrieved sources.
    If validation fails, the graph loops back to generation with feedback.
    """

    if state.insufficient_evidence or not state.retrieved_chunks:
        return {"validation_passed": True}

    is_valid, issues = await validator.validate(
        answer=state.generated_answer,
        chunks=state.retrieved_chunks,
        query=state.original_query,
    )

    logger.info(
        f"Validation: {'PASS' if is_valid else 'FAIL'} "
        f"(attempt {state.validation_attempts + 1}), issues: {issues}"
    )

    return {
        "validation_passed": is_valid,
        "validation_issues": issues,
        "validation_attempts": state.validation_attempts + 1,
    }


# ── Node: Finalize Response ──────────────────────────────────────────────────

async def finalize_response(state: AgentState) -> Dict[str, Any]:
    """
    Packages the final response with citations and metrics.
    """

    confidence = 0.0
    if state.retrieved_chunks:
        confidence = float(np.mean([c.relevance_score for c in state.retrieved_chunks]))

    latency_ms = int((time.time() - state.start_time) * 1000)

    return {
        "final_answer": state.generated_answer,
        "citations": state.retrieved_chunks,
        "confidence": confidence,
        "latency_ms": latency_ms,
        "insufficient_evidence": "INSUFFICIENT_EVIDENCE" in state.generated_answer,
    }


# ── Node: Handle Clarification ──────────────────────────────────────────────

async def handle_clarification(state: AgentState, llm_client) -> Dict[str, Any]:
    """
    When the query is too vague, generate a clarification request.
    """

    conv_context = ""
    if state.conversation_history:
        conv_context = "\n".join(
            f"{t.role}: {t.content[:200]}" for t in state.conversation_history[-4:]
        )

    prompt = f"""The user asked a medical research question that is too vague to search effectively.

{f'CONVERSATION HISTORY:{chr(10)}{conv_context}{chr(10)}' if conv_context else ''}
USER QUERY: {state.original_query}

Generate a helpful clarification request that:
1. Acknowledges what they're asking about
2. Suggests 2-3 specific directions they could take
3. Is professional and concise

CLARIFICATION:"""

    clarification, tokens = await llm_client.generate(prompt, max_tokens=300)

    return {
        "generated_answer": clarification,
        "tokens_used": tokens,
        "total_tokens": state.total_tokens + tokens,
        "insufficient_evidence": False,
    }


# ── Prompt Builders (private) ────────────────────────────────────────────────

def _build_qa_prompt(context: str, question: str, history: str) -> str:
    return f"""You are a specialized healthcare research assistant that helps medical professionals 
understand medical literature.

STRICT RULES — NEVER VIOLATE:
1. Answer ONLY from the provided context. Never use external knowledge.
2. Every factual claim MUST be supported by a citation [1], [2], etc.
3. If the context does not contain enough information, respond with INSUFFICIENT_EVIDENCE.
4. Never speculate, extrapolate, or make diagnostic suggestions.
5. Use precise medical terminology from the source documents.
6. Always end with: "⚠️ This is not medical advice. Consult a qualified healthcare professional."

{history}CONTEXT FROM MEDICAL LITERATURE:
{context}

QUESTION: {question}

Provide a thorough, evidence-based answer with inline citations.

ANSWER:"""


def _build_summarize_prompt(context: str, question: str, history: str) -> str:
    return f"""You are summarizing medical research. Use ONLY the provided text.

{history}DOCUMENT EXCERPTS:
{context}

{f'FOCUS AREA: {question}' if question else ''}

Provide a structured summary with:
1. **Study Objective** — What question does this research address?
2. **Methodology** — Study design and methods used.
3. **Key Findings** — Main results with citations [1], [2], etc.
4. **Conclusions** — What the authors concluded.
5. **Limitations** — Any stated limitations.

⚠️ This is not medical advice. Consult a qualified healthcare professional."""


def _build_compare_prompt(context: str, question: str, history: str) -> str:
    return f"""You are comparing information from medical literature. Use ONLY the provided context.

{history}CONTEXT FROM MULTIPLE SOURCES:
{context}

COMPARISON REQUEST: {question}

Instructions:
- Compare and contrast the subjects using ONLY information from the context.
- Organize as a structured comparison (use categories like efficacy, side effects, dosage, etc.).
- Cite every claim with [1], [2], etc.
- Note where sources agree and where they differ.
- If evidence for comparison is insufficient, state so clearly.

⚠️ This is not medical advice. Consult a qualified healthcare professional.

COMPARISON:"""


def _build_extract_prompt(context: str, question: str, history: str) -> str:
    return f"""You are a medical data extraction specialist. Extract structured information 
from the provided medical literature context.

{history}CONTEXT:
{context}

EXTRACTION REQUEST: {question}

Instructions:
- Extract ONLY information present in the context above.
- Use inline citations [1], [2] for every extracted data point.
- Organize data in clear structured format (lists, categories, tables).
- If specific data is not available, note "Not found in provided documents."

⚠️ This is not medical advice. Consult a qualified healthcare professional.

EXTRACTED DATA:"""
