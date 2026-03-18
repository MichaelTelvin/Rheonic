# Authentication service for register/login.
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.input_validation import sanitize_email
from app.application.interfaces.refresh_session_repository import RefreshSessionRepository
from app.application.interfaces.user_repository import UserRepository
from app.config import Settings
from app.domain.models.refresh_session import RefreshSession
from app.domain.models.user import User
from app.security.jwt_tokens import create_access_token, create_refresh_token, decode_access_token
from app.security.passwords import hash_password, verify_password


class AuthService:
    # Handles user registration and login.

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_session_repository: RefreshSessionRepository,
        settings: Settings,
    ) -> None:
        # Initialize service dependencies.
        self._user_repository = user_repository
        self._refresh_session_repository = refresh_session_repository
        self._settings = settings

    def register(self, email: str, password: str) -> User:
        # Register a user account.
        normalized_email = sanitize_email(email)
        self._validate_password(password)
        if self._user_repository.get_by_email(normalized_email) is not None:
            raise HTTPException(status_code=409, detail="email already exists")
        user = User(
            id=str(uuid4()),
            email=normalized_email,
            password_hash=hash_password(password),
            created_at=datetime.now(timezone.utc),
        )
        return self._user_repository.create_user(user)

    def login(self, email: str, password: str) -> tuple[str, str, User]:
        # Validate credentials and issue access/refresh tokens.
        normalized_email = sanitize_email(email)
        user = self._user_repository.get_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid credentials")
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
            expires_minutes=self._settings.jwt_expires_min,
        )
        refresh_session = self._build_refresh_session(user_id=user.id)
        refresh_token = create_refresh_token(
            user_id=user.id,
            email=user.email,
            jti=refresh_session.jti,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
            expires_minutes=self._settings.jwt_refresh_expires_min,
        )
        self._refresh_session_repository.create_session(refresh_session)
        return access_token, refresh_token, user

    def refresh(self, refresh_token: str) -> tuple[str, str, User]:
        # Validate refresh token and rotate access/refresh tokens.
        payload = decode_access_token(
            token=refresh_token,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
        )
        if payload is None or str(payload.get("typ") or "") != "refresh":
            raise HTTPException(status_code=401, detail="invalid refresh token")
        user_id = str(payload.get("sub") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        current_jti = str(payload.get("jti") or "")
        if not current_jti:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        user = self._user_repository.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        current_session = self._refresh_session_repository.get_by_jti(current_jti)
        if current_session is None or current_session.user_id != user.id or current_session.revoked_at is not None:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
            expires_minutes=self._settings.jwt_expires_min,
        )
        next_refresh_session = self._build_refresh_session(user_id=user.id)
        next_refresh_token = create_refresh_token(
            user_id=user.id,
            email=user.email,
            jti=next_refresh_session.jti,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
            expires_minutes=self._settings.jwt_refresh_expires_min,
        )
        rotated = self._refresh_session_repository.rotate_session(
            current_jti=current_jti,
            replacement=next_refresh_session,
            revoked_at=datetime.now(timezone.utc),
        )
        if not rotated:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        return access_token, next_refresh_token, user

    def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        payload = decode_access_token(
            token=refresh_token,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
        )
        if payload is None or str(payload.get("typ") or "") != "refresh":
            return
        current_jti = str(payload.get("jti") or "")
        if not current_jti:
            return
        self._refresh_session_repository.revoke_session(
            jti=current_jti,
            revoked_at=datetime.now(timezone.utc),
        )

    def _validate_password(self, password: str) -> None:
        if len(password) < 12:
            raise HTTPException(status_code=400, detail="password must be at least 12 characters")
        if not any(char.islower() for char in password):
            raise HTTPException(status_code=400, detail="password must include a lowercase letter")
        if not any(char.isupper() for char in password):
            raise HTTPException(status_code=400, detail="password must include an uppercase letter")
        if not any(char.isdigit() for char in password):
            raise HTTPException(status_code=400, detail="password must include a number")
        if not any(not char.isalnum() for char in password):
            raise HTTPException(status_code=400, detail="password must include a symbol")

    def _build_refresh_session(self, *, user_id: str) -> RefreshSession:
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(minutes=self._settings.jwt_refresh_expires_min)
        return RefreshSession(
            jti=str(uuid4()),
            user_id=user_id,
            created_at=issued_at,
            expires_at=expires_at,
            revoked_at=None,
            replaced_by_jti=None,
        )
