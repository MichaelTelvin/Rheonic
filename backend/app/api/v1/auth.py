# Authentication endpoints.
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.application.services.auth_service import AuthService
from app.config import Settings
from app.dependencies import get_auth_service, get_current_user, get_settings
from app.domain.models.user import User

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
    # Session response with user info.
    user: UserOut


class LogoutOut(BaseModel):
    # Logout response payload.
    status: str


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.auth_access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=max(int(settings.jwt_expires_min), 1) * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=max(int(settings.jwt_refresh_expires_min), 1) * 60,
        path=f"{settings.api_prefix}/v1/auth",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_access_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path=f"{settings.api_prefix}/v1/auth",
    )


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
async def login(
    payload: AuthIn,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LoginOut:
    # Authenticate a user, set auth cookies, and return user info.
    try:
        access_token, refresh_token, user = service.login(email=payload.email, password=payload.password)
        _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token, settings=settings)
        logger.info("Login succeeded", extra={"user_id": user.id, "email": user.email})
        return LoginOut(
            user=UserOut(id=user.id, email=user.email, created_at=user.created_at),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Login endpoint failed")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh", response_model=LoginOut)
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LoginOut:
    # Issue a new auth cookie pair from a valid refresh cookie.
    try:
        refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
        if not refresh_token:
            logger.warning("Refresh rejected due to missing refresh cookie")
            raise HTTPException(status_code=401, detail="invalid refresh token")
        access_token, next_refresh_token, user = service.refresh(refresh_token=refresh_token)
        _set_auth_cookies(response, access_token=access_token, refresh_token=next_refresh_token, settings=settings)
        logger.info("Session refreshed", extra={"user_id": user.id, "email": user.email})
        return LoginOut(
            user=UserOut(id=user.id, email=user.email, created_at=user.created_at),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Refresh endpoint failed")
        raise HTTPException(status_code=500, detail="Refresh failed")


@router.post("/logout", response_model=LogoutOut)
async def logout(response: Response, settings: Settings = Depends(get_settings)) -> LogoutOut:
    # Clear auth cookies for the current browser session.
    try:
        _clear_auth_cookies(response, settings)
        logger.info("Logout completed")
        return LogoutOut(status="ok")
    except Exception:
        logger.exception("Logout endpoint failed")
        raise HTTPException(status_code=500, detail="Logout failed")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    # Return the current authenticated browser user.
    try:
        return UserOut(id=current_user.id, email=current_user.email, created_at=current_user.created_at)
    except Exception:
        logger.exception("Me endpoint failed")
        raise HTTPException(status_code=500, detail="Failed to fetch current user")
