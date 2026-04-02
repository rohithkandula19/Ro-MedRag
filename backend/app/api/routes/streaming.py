"""
Streaming RAG — Server-Sent Events endpoint for real-time token streaming.

This module adds SSE streaming to the RAG pipeline:
  1. Agent runs routing + retrieval (non-streamed, fast)
  2. LLM generation streams token-by-token via SSE
  3. Citations and metadata sent as final SSE event
  4. Frontend renders tokens as they arrive
"""

import json
import time
import asyncio
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.logging import get_logger
from app.db.database import get_session
from app.services.rag_pipeline import get_pipeline, RetrievedChunk, RAGResponse
from app.services.agent.state import AgentState, AgentAction, ConversationTurn
from app.models.user import ChatSession, Message, Citation

logger = get_logger(__name__)

router = APIRouter()


class StreamQueryRequest(BaseModel):
    question: str
    mode: str = "qa"


async def _stream_rag_response(
    session_id: str,
    question: str,
    mode: str,
    user_id: str,
    db_session: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    Generator that yields SSE events:
      - event: status   → agent status updates (routing, retrieving, etc.)
      - event: token    → individual tokens from LLM
      - event: citations → citation data as JSON
      - event: done     → final metadata (tokens, latency, confidence)
      - event: error    → error message
    """
    import anthropic

    pipeline = get_pipeline()
    start_time = time.time()

    try:
        # Validate session
        chat = await db_session.get(ChatSession, session_id)
        if not chat or chat.user_id != user_id:
            yield f"event: error\ndata: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        # Save user message
        user_msg = Message(session_id=session_id, role="user", content=question.strip())
        db_session.add(user_msg)
        await db_session.flush()

        # ── Phase 1: Agent routing + retrieval (non-streamed) ──────────
        yield f"event: status\ndata: {json.dumps({'step': 'routing', 'message': 'Analyzing query...'})}\n\n"

        # Build agent state
        conversation_history = pipeline.memory.get_history(session_id)
        state = AgentState(
            original_query=question.strip(),
            mode=mode,
            document_ids=chat.document_ids or None,
            conversation_history=conversation_history,
        )
        state.start_time = start_time

        # Route the query
        from app.services.agent import nodes
        updates = await nodes.route_query(state, pipeline.llm)
        for k, v in updates.items():
            if hasattr(state, k):
                setattr(state, k, v)

        yield f"event: status\ndata: {json.dumps({'step': 'routing_done', 'action': state.action.value, 'message': f'Action: {state.action.value}'})}\n\n"

        # Handle clarification (no retrieval needed)
        if state.action == AgentAction.CLARIFY:
            yield f"event: status\ndata: {json.dumps({'step': 'clarifying', 'message': 'Generating clarification...'})}\n\n"
            updates = await nodes.handle_clarification(state, pipeline.llm)
            for k, v in updates.items():
                if hasattr(state, k):
                    setattr(state, k, v)

            # Stream the clarification as tokens
            for word in state.generated_answer.split(' '):
                yield f"event: token\ndata: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(0.02)

            latency_ms = int((time.time() - start_time) * 1000)
            # Save message
            assistant_msg = Message(
                session_id=session_id, role="assistant", content=state.generated_answer,
                tokens_used=state.total_tokens, latency_ms=latency_ms,
                confidence_score=0.0, has_citations=False,
            )
            db_session.add(assistant_msg)
            await db_session.commit()

            yield f"event: done\ndata: {json.dumps({'tokens_used': state.total_tokens, 'latency_ms': latency_ms, 'confidence': 0.0, 'message_id': assistant_msg.id})}\n\n"
            return

        # ── Phase 2: Retrieval ─────────────────────────────────────────
        yield f"event: status\ndata: {json.dumps({'step': 'retrieving', 'message': 'Searching documents...'})}\n\n"

        # Run retrieval loop
        from app.services.agent.tools import SufficiencyEvaluator, QueryReformulationTool
        sufficiency_evaluator = SufficiencyEvaluator()
        reformulation_tool = QueryReformulationTool(pipeline.llm)

        if state.action == AgentAction.COMPARE:
            from app.services.agent.tools import ComparisonTool
            comparison_tool = ComparisonTool(pipeline.retrieval_tool)
            updates = await nodes.compare_documents(state, comparison_tool, pipeline.llm)
            for k, v in updates.items():
                if hasattr(state, k):
                    setattr(state, k, v)
        else:
            # Standard retrieval with re-query loop
            while state.retrieval_attempts < state.max_retrieval_attempts:
                updates = await nodes.retrieve_context(state, pipeline.retrieval_tool)
                for k, v in updates.items():
                    if hasattr(state, k):
                        setattr(state, k, v)

                updates = await nodes.evaluate_sufficiency(state, sufficiency_evaluator)
                for k, v in updates.items():
                    if hasattr(state, k):
                        setattr(state, k, v)

                if state.retrieval_sufficient:
                    break
                if state.retrieval_attempts >= state.max_retrieval_attempts:
                    break

                yield f"event: status\ndata: {json.dumps({'step': 'reformulating', 'message': f'Refining search (attempt {state.retrieval_attempts})...'})}\n\n"
                updates = await nodes.reformulate_query(state, reformulation_tool)
                for k, v in updates.items():
                    if hasattr(state, k):
                        setattr(state, k, v)

        yield f"event: status\ndata: {json.dumps({'step': 'retrieved', 'chunks': len(state.retrieved_chunks), 'message': f'Found {len(state.retrieved_chunks)} relevant passages'})}\n\n"

        # ── Phase 3: Streaming generation ──────────────────────────────
        if not state.retrieved_chunks:
            answer = (
                "INSUFFICIENT_EVIDENCE: The provided documents do not contain "
                "enough information to answer this question reliably.\n\n"
                "⚠️ This is not medical advice. Consult a qualified healthcare professional."
            )
            for word in answer.split(' '):
                yield f"event: token\ndata: {json.dumps({'token': word + ' '})}\n\n"
                await asyncio.sleep(0.02)

            latency_ms = int((time.time() - start_time) * 1000)
            assistant_msg = Message(
                session_id=session_id, role="assistant", content=answer,
                tokens_used=0, latency_ms=latency_ms,
                confidence_score=0.0, has_citations=False,
            )
            db_session.add(assistant_msg)
            await db_session.commit()
            yield f"event: done\ndata: {json.dumps({'tokens_used': 0, 'latency_ms': latency_ms, 'confidence': 0.0, 'message_id': assistant_msg.id})}\n\n"
            return

        yield f"event: status\ndata: {json.dumps({'step': 'generating', 'message': 'Generating response...'})}\n\n"

        # Build prompt
        context_parts = []
        for chunk in state.retrieved_chunks:
            context_parts.append(
                f"[{chunk.citation_index}] (Source: {chunk.document_filename}, "
                f"Page {chunk.page_number or 'N/A'}):\n{chunk.content}"
            )
        context = "\n\n---\n\n".join(context_parts)

        history_section = ""
        if state.conversation_history:
            recent = state.conversation_history[-6:]
            history_parts = [f"{t.role.upper()}: {t.content[:300]}" for t in recent]
            history_section = f"CONVERSATION HISTORY:\n{chr(10).join(history_parts)}\n\n"

        system_prompt = """You are a specialized healthcare research assistant that helps medical professionals and researchers understand medical literature.

STRICT RULES — NEVER VIOLATE:
1. Answer ONLY from the provided context. Never use external knowledge.
2. Every factual claim MUST be supported by a citation [1], [2], etc.
3. If the context does not contain enough information, respond with INSUFFICIENT_EVIDENCE.
4. Never speculate, extrapolate, or make diagnostic suggestions.
5. Use precise medical terminology from the source documents.
6. Always end with: "⚠️ This is not medical advice. Consult a qualified healthcare professional."
"""

        if state.action == AgentAction.SUMMARIZE:
            user_prompt = f"""{history_section}DOCUMENT EXCERPTS:\n{context}\n\nProvide a structured summary with Study Objective, Methodology, Key Findings, Conclusions, and Limitations. Cite with [1], [2].\n\n⚠️ This is not medical advice."""
        elif state.action == AgentAction.COMPARE:
            user_prompt = f"""{history_section}CONTEXT FROM MULTIPLE SOURCES:\n{context}\n\nCOMPARISON REQUEST: {state.original_query}\n\nCompare using ONLY the context. Cite with [1], [2]. Note agreements and differences.\n\n⚠️ This is not medical advice."""
        elif state.action == AgentAction.EXTRACT:
            user_prompt = f"""{history_section}CONTEXT:\n{context}\n\nEXTRACTION REQUEST: {state.original_query}\n\nExtract structured data with citations [1], [2].\n\n⚠️ This is not medical advice."""
        else:
            user_prompt = f"""{history_section}CONTEXT FROM MEDICAL LITERATURE:\n{context}\n\nQUESTION: {state.original_query}\n\nProvide a thorough, evidence-based answer with inline citations [1], [2].\n\nANSWER:"""

        # Stream from Claude
        full_answer = ""
        total_tokens = state.total_tokens
        client = anthropic.AsyncAnthropic(api_key=pipeline.llm.client.api_key)

        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                full_answer += text
                yield f"event: token\ndata: {json.dumps({'token': text})}\n\n"

        # Get final usage
        response = await stream.get_final_message()
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        # ── Phase 4: Send citations ────────────────────────────────────
        import numpy as np
        confidence = float(np.mean([c.relevance_score for c in state.retrieved_chunks]))
        latency_ms = int((time.time() - start_time) * 1000)

        citations_data = [
            {
                "citation_index": c.citation_index,
                "document_filename": c.document_filename,
                "page_number": c.page_number,
                "chunk_content": c.content,
                "relevance_score": round(c.relevance_score, 3),
            }
            for c in state.retrieved_chunks
        ]

        yield f"event: citations\ndata: {json.dumps({'citations': citations_data})}\n\n"

        # ── Phase 5: Save to database ──────────────────────────────────
        assistant_msg = Message(
            session_id=session_id, role="assistant", content=full_answer,
            tokens_used=total_tokens, latency_ms=latency_ms,
            confidence_score=confidence, has_citations=bool(state.retrieved_chunks),
        )
        db_session.add(assistant_msg)
        await db_session.flush()

        # Save citations (with error handling for FK issues)
        for chunk in state.retrieved_chunks:
            try:
                citation = Citation(
                    message_id=assistant_msg.id,
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    chunk_content=chunk.content,
                    relevance_score=chunk.relevance_score,
                    page_number=chunk.page_number,
                    document_filename=chunk.document_filename,
                    citation_index=chunk.citation_index,
                )
                db_session.add(citation)
            except Exception as e:
                logger.warning(f"Citation save skipped: {e}")

        from datetime import datetime, timezone
        chat.updated_at = datetime.now(timezone.utc)

        try:
            await db_session.commit()
        except Exception as e:
            logger.warning(f"Citation commit failed, saving message only: {e}")
            await db_session.rollback()
            db_session.add(assistant_msg)
            await db_session.commit()

        # Update conversation memory
        pipeline.memory.add_turn(session_id, "user", question.strip())
        pipeline.memory.add_turn(session_id, "assistant", full_answer)

        yield f"event: done\ndata: {json.dumps({'tokens_used': total_tokens, 'latency_ms': latency_ms, 'confidence': round(confidence, 3), 'message_id': assistant_msg.id})}\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.post("/sessions/{session_id}/stream")
async def stream_query(
    session_id: str,
    body: StreamQueryRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """SSE streaming endpoint for real-time RAG responses."""

    if not body.question.strip() or len(body.question.strip()) < 3:
        raise HTTPException(400, "Question too short")
    if len(body.question) > 2000:
        raise HTTPException(400, "Question too long")

    return StreamingResponse(
        _stream_rag_response(
            session_id=session_id,
            question=body.question.strip(),
            mode=body.mode,
            user_id=current_user.id,
            db_session=session,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
