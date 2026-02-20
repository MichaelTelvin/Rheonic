# Authentication endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.application.services.auth_service import AuthService
from app.dependencies import get_auth_service

from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class AuthIn(BaseModel):
    # Auth request payload.
    email: str
    password: str


class UserOut(BaseModel):
    # Public user response model.
    id: str
    email: str
    created_at: datetime


class LoginOut(BaseModel):
    # Login response with access token and user info.
    access_token: str
    refresh_token: str
    token_type: str
    user: UserOut


class RefreshIn(BaseModel):
    # Refresh request payload.
    refresh_token: str


@router.post("/register", response_model=UserOut)
async def register(payload: AuthIn, service: AuthService = Depends(get_auth_service)) -> UserOut:
    # Register user account.
    try:
        user = service.register(email=payload.email, password=payload.password)
        return UserOut(id=user.id, email=user.email, created_at=user.created_at)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Register endpoint failed")
        raise HTTPException(status_code=500, detail="Register failed")


@router.post("/login", response_model=LoginOut)
async def login(payload: AuthIn, service: AuthService = Depends(get_auth_service)) -> LoginOut:
    # Authenticate a user and issue access token.
    try:
        access_token, refresh_token, user = service.login(email=payload.email, password=payload.password)
        return LoginOut(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserOut(id=user.id, email=user.email, created_at=user.created_at),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login endpoint failed")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh", response_model=LoginOut)
async def refresh(payload: RefreshIn, service: AuthService = Depends(get_auth_service)) -> LoginOut:
    # Issue a new access token from a valid refresh token.
    try:
        access_token, refresh_token, user = service.refresh(refresh_token=payload.refresh_token)
        return LoginOut(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserOut(id=user.id, email=user.email, created_at=user.created_at),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Refresh endpoint failed")
        raise HTTPException(status_code=500, detail="Refresh failed")
