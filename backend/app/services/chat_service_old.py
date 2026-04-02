"""Chat service — manages sessions, messages, and RAG queries."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.user import ChatSession, Message, Citation, Document
from app.services.rag_pipeline import get_pipeline, RAGResponse

logger = get_logger(__name__)


class ChatService:

    @staticmethod
    async def create_session(
        user_id: str,
        title: Optional[str],
        document_ids: Optional[List[str]],
        session: AsyncSession,
    ) -> ChatSession:
        chat = ChatSession(
            user_id=user_id,
            title=title or "New Research Session",
            document_ids=document_ids or [],
        )
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
        return chat

    @staticmethod
    async def get_session(
        session_id: str, user_id: str, session: AsyncSession
    ) -> ChatSession:
        chat = await session.get(ChatSession, session_id)
        if not chat:
            raise HTTPException(404, "Session not found")
        if chat.user_id != user_id:
            raise HTTPException(403, "Access denied")
        return chat

    @staticmethod
    async def list_sessions(user_id: str, session: AsyncSession) -> List[ChatSession]:
        q = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
        result = await session.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def get_messages(
        session_id: str, user_id: str, session: AsyncSession
    ) -> List[Message]:
        chat = await ChatService.get_session(session_id, user_id, session)
        q = (
            select(Message)
            .where(Message.session_id == session_id)
            .options(selectinload(Message.citations))
            .order_by(Message.created_at.asc())
        )
        result = await session.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def query(
        session_id: str,
        user_id: str,
        question: str,
        mode: str,
        db_session: AsyncSession,
    ) -> Message:
        """Run RAG pipeline and persist message + citations."""

        chat = await ChatService.get_session(session_id, user_id, db_session)

        # Validate question
        if not question.strip() or len(question.strip()) < 3:
            raise HTTPException(400, "Question too short")
        if len(question) > 2000:
            raise HTTPException(400, "Question too long (max 2000 chars)")

        # Save user message
        user_msg = Message(
            session_id=session_id,
            role="user",
            content=question.strip(),
        )
        db_session.add(user_msg)

        # Run RAG
        pipeline = get_pipeline()
        rag_result: RAGResponse = await pipeline.query(
            question=question.strip(),
            document_ids=chat.document_ids or None,
            mode=mode,
        )

        # Save assistant message
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=rag_result.answer,
            tokens_used=rag_result.tokens_used,
            latency_ms=rag_result.latency_ms,
            confidence_score=rag_result.confidence,
            has_citations=bool(rag_result.citations),
        )
        db_session.add(assistant_msg)
        await db_session.flush()  # get assistant_msg.id

        # Save citations
        for chunk in rag_result.citations:
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

        # Update session updated_at
        chat.updated_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(assistant_msg)

        return assistant_msg

    @staticmethod
    async def delete_session(
        session_id: str, user_id: str, session: AsyncSession
    ):
        chat = await ChatService.get_session(session_id, user_id, session)
        await session.delete(chat)
        await session.commit()
