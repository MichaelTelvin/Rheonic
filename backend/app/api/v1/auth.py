# Authentication endpoints.
import hashlib
import time
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.application.services.auth_service import AuthService
from app.config import Settings
from app.dependencies import get_auth_service, get_current_user, get_redis_client, get_settings
from app.domain.models.user import User
from app.infrastructure.redis.redis_client import RedisClient
from app.logger import build_log_extra, get_logger

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


def _hash_rate_limit_fragment(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    return (request.client.host if request.client is not None else "") or "unknown"


def _auth_rate_limit_key(scope: str, discriminator: str, window_epoch: int) -> str:
    return f"auth_rl:{scope}:{_hash_rate_limit_fragment(discriminator)}:{window_epoch}"


def _enforce_auth_rate_limit(
    *,
    redis_client: RedisClient,
    settings: Settings,
    request: Request,
    scope: str,
    limit: int,
    email: str | None = None,
) -> None:
    window_seconds = max(int(settings.auth_rate_limit_window_seconds), 1)
    window_epoch = int(time.time()) // window_seconds
    client_ip = _client_ip(request, settings)
    discriminator_parts = [scope, client_ip]
    if email:
        discriminator_parts.append(email.strip().lower())
    discriminator = "|".join(discriminator_parts)
    key = _auth_rate_limit_key(scope, discriminator, window_epoch)
    try:
        counter = redis_client.incr(key)
        if counter == 1:
            redis_client.expire(key, window_seconds)
        if counter > limit:
            logger.warning(
                "Auth rate limit exceeded",
                extra=build_log_extra(
                    event="auth_rate_limited",
                    metadata={
                        "scope": scope,
                        "client_ip": client_ip,
                    },
                    trace_id=getattr(request.state, "trace_id", None),
                    span_id=getattr(request.state, "span_id", None),
                ),
            )
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        logger.warning(
            "Auth rate-limit Redis unavailable; processing auth in fail-open mode",
            extra=build_log_extra(
                event="cache_unavailable",
                metadata={"component": "auth_rate_limit", "scope": scope},
                trace_id=getattr(request.state, "trace_id", None),
                span_id=getattr(request.state, "span_id", None),
            ),
        )


def _set_auth_cookies(response: Response, *, access_token: str, refresh_token: str, settings: Settings) -> None:
    same_site = _cookie_samesite(settings.auth_cookie_samesite)
    response.set_cookie(
        key=settings.auth_access_cookie_name,
        value=access_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=same_site,
        max_age=max(int(settings.jwt_expires_min), 1) * 60,
        path="/",
    )
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=same_site,
        max_age=max(int(settings.jwt_refresh_expires_min), 1) * 60,
        path=f"{settings.api_prefix}/v1/auth",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    same_site = _cookie_samesite(settings.auth_cookie_samesite)
    response.delete_cookie(
        key=settings.auth_access_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=same_site,
        path="/",
    )
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=same_site,
        path=f"{settings.api_prefix}/v1/auth",
    )


def _cookie_samesite(value: str) -> Literal["lax", "strict", "none"]:
    normalized = value.lower()
    if normalized in {"lax", "strict", "none"}:
        return cast(Literal["lax", "strict", "none"], normalized)
    return "lax"


@router.post("/register", response_model=UserOut)
async def register(
    payload: AuthIn,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    redis_client: RedisClient = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    # Register user account.
    try:
        _enforce_auth_rate_limit(
            redis_client=redis_client,
            settings=settings,
            request=request,
            scope="register",
            limit=settings.auth_register_rate_limit_per_window,
        )
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
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    redis_client: RedisClient = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> LoginOut:
    # Authenticate a user, set auth cookies, and return user info.
    try:
        _enforce_auth_rate_limit(
            redis_client=redis_client,
            settings=settings,
            request=request,
            scope="login",
            limit=settings.auth_login_rate_limit_per_window,
            email=payload.email,
        )
        access_token, refresh_token, user = service.login(email=payload.email, password=payload.password)
        _set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token, settings=settings)
        logger.info("Login succeeded", extra={"user_id": user.id})
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
    redis_client: RedisClient = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> LoginOut:
    # Issue a new auth cookie pair from a valid refresh cookie.
    try:
        _enforce_auth_rate_limit(
            redis_client=redis_client,
            settings=settings,
            request=request,
            scope="refresh",
            limit=settings.auth_refresh_rate_limit_per_window,
        )
        refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
        if not refresh_token:
            logger.warning("Refresh rejected due to missing refresh cookie")
            raise HTTPException(status_code=401, detail="invalid refresh token")
        access_token, next_refresh_token, user = service.refresh(refresh_token=refresh_token)
        _set_auth_cookies(response, access_token=access_token, refresh_token=next_refresh_token, settings=settings)
        logger.info("Session refreshed", extra={"user_id": user.id})
        return LoginOut(
            user=UserOut(id=user.id, email=user.email, created_at=user.created_at),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Refresh endpoint failed")
        raise HTTPException(status_code=500, detail="Refresh failed")


@router.post("/logout", response_model=LogoutOut)
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> LogoutOut:
    # Clear auth cookies for the current browser session.
    try:
        service.logout(request.cookies.get(settings.auth_refresh_cookie_name))
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
