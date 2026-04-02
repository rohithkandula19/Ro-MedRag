"""Document service — upload validation, async processing, management."""

import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import UploadFile, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import Document, DocumentChunk
from app.services.rag_pipeline import get_pipeline

logger = get_logger(__name__)

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


class DocumentService:

    @staticmethod
    async def upload_and_process(
        file: UploadFile,
        owner_id: str,
        session: AsyncSession,
    ) -> Document:
        """Validate, save, persist metadata, then trigger async ingestion."""

        # ── Validation ──────────────────────────────────────────────────
        ext = Path(file.filename or "").suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type '{ext}' not allowed. Only PDF supported.")

        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(413, f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB.")
        if len(content) < 100:
            raise HTTPException(400, "File appears to be empty or corrupt.")

        # ── Persist file ─────────────────────────────────────────────────
        doc_id = str(uuid.uuid4())
        safe_name = f"{doc_id}{ext}"
        file_path = UPLOAD_DIR / safe_name
        file_path.write_bytes(content)

        # ── DB record ────────────────────────────────────────────────────
        doc = Document(
            id=doc_id,
            owner_id=owner_id,
            filename=safe_name,
            original_filename=file.filename or safe_name,
            file_path=str(file_path),
            file_size_bytes=len(content),
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        # ── Async ingestion ───────────────────────────────────────────────
        import asyncio
        asyncio.create_task(
            DocumentService._ingest(doc_id, str(file_path), file.filename or safe_name, session)
        )

        return doc

    @staticmethod
    async def _ingest(doc_id: str, file_path: str, filename: str, session: AsyncSession):
        """Background task: RAG ingestion + chunk storage."""
        from app.db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_session:
            try:
                pipeline = get_pipeline()
                chunks = await pipeline.ingest_document(file_path, doc_id, filename)

                # Persist chunks
                chunk_records = [
                    DocumentChunk(
                        document_id=doc_id,
                        chunk_index=c.chunk_index,
                        content=c.content,
                        page_number=c.page_number,
                        token_count=c.token_count,
                        embedding_id=f"{doc_id}_{c.chunk_index}",
                    )
                    for c in chunks
                ]
                bg_session.add_all(chunk_records)

                # Update document status
                doc = await bg_session.get(Document, doc_id)
                if doc:
                    doc.status = "ready"
                    doc.chunk_count = len(chunks)
                    doc.processed_at = datetime.now(timezone.utc)

                await bg_session.commit()
                logger.info(f"Document {doc_id} ingested: {len(chunks)} chunks")

            except Exception as e:
                logger.error(f"Ingestion failed for {doc_id}: {e}", exc_info=True)
                async with AsyncSessionLocal() as err_session:
                    doc = await err_session.get(Document, doc_id)
                    if doc:
                        doc.status = "failed"
                        doc.error_message = str(e)[:500]
                        await err_session.commit()

    @staticmethod
    async def list_documents(
        owner_id: str,
        session: AsyncSession,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Document]:
        q = select(Document).where(Document.owner_id == owner_id)
        if status:
            q = q.where(Document.status == status)
        if search:
            q = q.where(Document.original_filename.ilike(f"%{search}%"))
        q = q.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def delete_document(doc_id: str, owner_id: str, session: AsyncSession):
        doc = await session.get(Document, doc_id)
        if not doc:
            raise HTTPException(404, "Document not found")
        if doc.owner_id != owner_id:
            raise HTTPException(403, "Access denied")

        # Remove from vector store
        try:
            get_pipeline().remove_document(doc_id)
        except Exception as e:
            logger.warning(f"Vector store cleanup failed: {e}")

        # Remove file
        try:
            os.remove(doc.file_path)
        except FileNotFoundError:
            pass

        await session.delete(doc)
        await session.commit()
