"""Admin routes — stats and user management."""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.database import get_session
from app.models.user import User, Document, Message

router = APIRouter()


@router.get("/stats")
async def get_stats(
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user_count = (await session.execute(select(func.count(User.id)))).scalar()
    doc_count = (await session.execute(select(func.count(Document.id)))).scalar()
    msg_count = (await session.execute(select(func.count(Message.id)))).scalar()
    return {
        "total_users": user_count,
        "total_documents": doc_count,
        "total_messages": msg_count,
    }


@router.get("/users")
async def list_users(
    _=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).order_by(User.created_at.desc()).limit(100))
    users = result.scalars().all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "is_active": u.is_active, "is_admin": u.is_admin} for u in users]
