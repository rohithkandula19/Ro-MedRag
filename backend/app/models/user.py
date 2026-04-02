"""All database models."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base

# ── Helpers ──────────────────────────────────────────────────────────────────

def utcnow():
    return datetime.now(timezone.utc)

def new_uuid():
    return str(uuid.uuid4())


# ── User ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    documents: Mapped[List["Document"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ── Document ──────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending | processing | ready | failed
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    doc_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    owner: Mapped["User"] = relationship(back_populates="documents")
    chunks: Mapped[List["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


# ── DocumentChunk ─────────────────────────────────────────────────────────────

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    section_title: Mapped[Optional[str]] = mapped_column(String(512))
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255))  # FAISS / Pinecone ID
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="chunks")


# ── ChatSession ───────────────────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    document_ids: Mapped[Optional[list]] = mapped_column(JSON)  # scoped documents
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")


# ── Message ───────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    has_citations: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    citations: Mapped[List["Citation"]] = relationship(back_populates="message", cascade="all, delete-orphan")


# ── Citation ──────────────────────────────────────────────────────────────────

class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_chunks.id"), nullable=False)
    chunk_content: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer)
    document_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False)  # [1], [2], etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped["Message"] = relationship(back_populates="citations")


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64))
    resource_id: Mapped[Optional[str]] = mapped_column(String(36))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(512))
    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
