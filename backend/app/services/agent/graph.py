"""
Agent Graph — the LangGraph workflow definition.

This is the heart of the agent. It defines:
  - Which nodes exist
  - How they connect (edges)
  - Conditional routing (when to loop, when to proceed)

Graph topology:
  ┌──────────┐
  │  Router  │
  └────┬─────┘
       │
  ┌────┴─────────────┬──────────┬──────────┐
  ▼                  ▼          ▼          ▼
Retrieve          Compare    Clarify   (Summarize→Retrieve)
  │                  │          │
  ▼                  │          ▼
Evaluate             │       Finalize
Sufficiency          │
  │                  │
  ├─ sufficient ─────┼──────────┐
  │                  │          │
  ├─ insufficient    │          │
  │   & retries left │          │
  │     │            │          │
  │     ▼            │          │
  │  Reformulate     │          │
  │     │            │          │
  │     └──→ Retrieve│          │
  │                  │          │
  ▼                  ▼          │
Generate ◀──────────┘          │
  │                            │
  ▼                            │
Validate                       │
  │                            │
  ├─ valid ───────────────────►│
  │                            ▼
  ├─ invalid & retries left  Finalize
  │     │
  │     └──→ Generate
  │
  ▼
Finalize
"""

import time
from typing import Any, Dict, Optional

from app.core.logging import get_logger
from app.services.agent.state import AgentAction, AgentState, RetrievedChunk
from app.services.agent import nodes
from app.services.agent.tools import (
    AnswerValidator,
    ComparisonTool,
    QueryReformulationTool,
    RetrievalTool,
    SufficiencyEvaluator,
)

logger = get_logger(__name__)


class MedRAGAgent:
    """
    The LangGraph-style agent that orchestrates the full RAG flow.

    Uses a manual graph implementation for maximum clarity and control.
    (Can be migrated to langgraph library with minimal changes.)

    The agent:
      1. Routes the query to the right action
      2. Retrieves relevant context (with re-query loops)
      3. Generates an answer
      4. Validates the answer (with self-correction loops)
      5. Finalizes with citations and metrics
    """

    def __init__(self, llm_client, retrieval_tool, reranker):
        self.llm = llm_client
        self.retrieval_tool = retrieval_tool
        self.reformulation_tool = QueryReformulationTool(llm_client)
        self.comparison_tool = ComparisonTool(retrieval_tool)
        self.sufficiency_evaluator = SufficiencyEvaluator()
        self.answer_validator = AnswerValidator(llm_client)

    async def run(self, state: AgentState) -> AgentState:
        """
        Execute the full agent graph.
        Returns the final state with answer, citations, and metrics.
        """
        state.start_time = time.time()

        try:
            # ── Step 1: Route ──────────────────────────────────────────
            updates = await nodes.route_query(state, self.llm)
            state = self._apply_updates(state, updates)

            # ── Step 2: Action dispatch ────────────────────────────────
            if state.action == AgentAction.CLARIFY:
                updates = await nodes.handle_clarification(state, self.llm)
                state = self._apply_updates(state, updates)
                updates = await nodes.finalize_response(state)
                state = self._apply_updates(state, updates)
                return state

            if state.action == AgentAction.COMPARE:
                updates = await nodes.compare_documents(
                    state, self.comparison_tool, self.llm
                )
                state = self._apply_updates(state, updates)
            else:
                # Standard retrieval (for RETRIEVE, SUMMARIZE, EXTRACT)
                state = await self._retrieval_loop(state)

            # ── Step 3: Generate ───────────────────────────────────────
            state = await self._generation_loop(state)

            # ── Step 4: Finalize ───────────────────────────────────────
            updates = await nodes.finalize_response(state)
            state = self._apply_updates(state, updates)

        except Exception as e:
            logger.error(f"Agent error: {e}", exc_info=True)
            state.error = str(e)
            state.final_answer = (
                "An error occurred while processing your query. "
                "Please try again.\n\n"
                "⚠️ This is not medical advice. Consult a qualified healthcare professional."
            )
            state.latency_ms = int((time.time() - state.start_time) * 1000)

        return state

    async def _retrieval_loop(self, state: AgentState) -> AgentState:
        """
        Retrieval loop with automatic re-query.

        Flow:
          Retrieve → Evaluate → (sufficient? → proceed) or (reformulate → retry)
        """
        while state.retrieval_attempts < state.max_retrieval_attempts:
            # Retrieve
            updates = await nodes.retrieve_context(state, self.retrieval_tool)
            state = self._apply_updates(state, updates)

            # Evaluate sufficiency
            updates = await nodes.evaluate_sufficiency(
                state, self.sufficiency_evaluator
            )
            state = self._apply_updates(state, updates)

            if state.retrieval_sufficient:
                break

            # Not sufficient — can we retry?
            if state.retrieval_attempts >= state.max_retrieval_attempts:
                logger.info("Max retrieval attempts reached, proceeding with available chunks")
                break

            # Reformulate query and retry
            updates = await nodes.reformulate_query(state, self.reformulation_tool)
            state = self._apply_updates(state, updates)

        return state

    async def _generation_loop(self, state: AgentState) -> AgentState:
        """
        Generation loop with self-correction.

        Flow:
          Generate → Validate → (valid? → proceed) or (regenerate with feedback)
        """
        while state.validation_attempts < state.max_validation_attempts:
            # Generate
            updates = await nodes.generate_answer(state, self.llm)
            state = self._apply_updates(state, updates)

            # Validate
            updates = await nodes.validate_answer(state, self.answer_validator)
            state = self._apply_updates(state, updates)

            if state.validation_passed:
                break

            # Validation failed — append issues to guide regeneration
            if state.validation_attempts >= state.max_validation_attempts:
                logger.warning("Max validation attempts reached, using last answer")
                break

            logger.info(f"Regenerating answer due to: {state.validation_issues}")

        return state

    def _apply_updates(self, state: AgentState, updates: Dict[str, Any]) -> AgentState:
        """Apply a dict of updates to the state."""
        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state
