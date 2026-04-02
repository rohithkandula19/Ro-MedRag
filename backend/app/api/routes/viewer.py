"""
PDF Viewer Service — serve PDFs with page-level citation linking.

Provides:
  - PDF file serving with proper headers
  - Page-specific URL generation for citation deep-links
  - PDF metadata extraction for the viewer component
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db.database import get_session
from app.models.user import Document
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/{document_id}/pdf")
async def serve_pdf(
    document_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Serve the original PDF file for the citation viewer."""

    # Get document
    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.owner_id != current_user.id:
        raise HTTPException(403, "Access denied")

    # Find file on disk
    file_path = os.path.join(settings.UPLOAD_DIR, doc.stored_filename or doc.filename)
    if not os.path.exists(file_path):
        # Try alternative path patterns
        for pattern in [
            os.path.join(settings.UPLOAD_DIR, f"{document_id}.pdf"),
            os.path.join(settings.UPLOAD_DIR, doc.filename),
        ]:
            if os.path.exists(pattern):
                file_path = pattern
                break
        else:
            raise HTTPException(404, "PDF file not found on disk")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=doc.filename,
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{document_id}/info")
async def get_pdf_info(
    document_id: str,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get PDF metadata for the viewer."""

    doc = await session.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.owner_id != current_user.id:
        raise HTTPException(403, "Access denied")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "page_count": doc.page_count,
        "file_size_bytes": doc.file_size_bytes,
        "status": doc.status,
        "viewer_url": f"/api/viewer/{document_id}/pdf",
    }
