"""Documents API — upload, list, delete, status."""

from typing import Optional
from fastapi import APIRouter, Depends, File, UploadFile, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.database import get_session
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("/upload", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentService.upload_and_process(file, current_user.id, session)
    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "status": doc.status,
        "file_size_bytes": doc.file_size_bytes,
        "message": "Document uploaded. Processing in background.",
    }


@router.get("/")
async def list_documents(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    docs = await DocumentService.list_documents(
        current_user.id, session, status, search, limit, offset
    )
    return [
        {
            "id": d.id,
            "filename": d.original_filename,
            "status": d.status,
            "file_size_bytes": d.file_size_bytes,
            "chunk_count": d.chunk_count,
            "page_count": d.page_count,
            "created_at": d.created_at.isoformat(),
            "processed_at": d.processed_at.isoformat() if d.processed_at else None,
            "error_message": d.error_message,
        }
        for d in docs
    ]


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from fastapi import HTTPException
    doc = await session.get(__import__("app.models.user", fromlist=["Document"]).Document, doc_id)
    if not doc or doc.owner_id != current_user.id:
        raise HTTPException(404, "Document not found")
    return {
        "id": doc.id,
        "filename": doc.original_filename,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "page_count": doc.page_count,
        "created_at": doc.created_at.isoformat(),
    }


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await DocumentService.delete_document(doc_id, current_user.id, session)
