"""Auth routes."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.services.user_service import UserService
from app.core.security import get_current_user

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = await UserService.create(body.email, body.password, body.full_name, session)
    return {"id": user.id, "email": user.email, "full_name": user.full_name}


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    return await UserService.authenticate(body.email, body.password, session)


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
    }
