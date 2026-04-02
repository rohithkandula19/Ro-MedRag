"""User CRUD and auth service."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.models.user import User


class UserService:

    @staticmethod
    async def create(email: str, password: str, full_name: str, session: AsyncSession) -> User:
        existing = await UserService.get_by_email(session, email)
        if existing:
            raise HTTPException(400, "Email already registered")
        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[User]:
        q = select(User).where(User.email == email.lower().strip())
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
        return await session.get(User, user_id)

    @staticmethod
    async def authenticate(email: str, password: str, session: AsyncSession):
        user = await UserService.get_by_email(session, email)
        if not user or not verify_password(password, user.hashed_password):
            raise HTTPException(401, "Invalid email or password")
        if not user.is_active:
            raise HTTPException(403, "Account disabled")
        user.last_login = datetime.now(timezone.utc)
        await session.commit()
        access_token = create_access_token({"sub": user.id})
        refresh_token = create_refresh_token({"sub": user.id})
        return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}
