"""Chat API — sessions, messages, RAG query."""

from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.database import get_session
from app.services.chat_service import ChatService

router = APIRouter()


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    document_ids: Optional[List[str]] = None


class QueryRequest(BaseModel):
    question: str
    mode: str = "qa"  # "qa" | "summarize"


def _serialize_message(msg):
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "tokens_used": msg.tokens_used,
        "latency_ms": msg.latency_ms,
        "confidence_score": msg.confidence_score,
        "has_citations": msg.has_citations,
        "created_at": msg.created_at.isoformat(),
        "citations": [
            {
                "citation_index": c.citation_index,
                "document_filename": c.document_filename,
                "page_number": c.page_number,
                "chunk_content": c.chunk_content,
                "relevance_score": round(c.relevance_score, 3),
            }
            for c in (msg.citations or [])
        ],
    }


@router.post("/sessions", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chat = await ChatService.create_session(
        current_user.id, body.title, body.document_ids, session
    )
    return {"id": chat.id, "title": chat.title, "created_at": chat.created_at.isoformat()}


@router.get("/sessions")
async def list_sessions(
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    sessions = await ChatService.list_sessions(current_user.id, session)
    return [
        {
            "id": s.id,
            "title": s.title,
            "document_ids": s.document_ids,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    messages = await ChatService.get_messages(session_id, current_user.id, session)
    return [_serialize_message(m) for m in messages]


@router.post("/sessions/{session_id}/query")
async def query(
    session_id: str,
    body: QueryRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    msg = await ChatService.query(
        session_id, current_user.id, body.question, body.mode, session
    )
    # Reload with citations
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import Message
    q = select(Message).where(Message.id == msg.id).options(selectinload(Message.citations))
    result = await session.execute(q)
    msg = result.scalar_one()
    return _serialize_message(msg)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ChatService.delete_session(session_id, current_user.id, session)
