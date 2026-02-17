# Authentication service for register/login.
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.application.input_validation import sanitize_email
from app.application.interfaces.user_repository import UserRepository
from app.config import Settings
from app.domain.models.user import User
from app.security.jwt_tokens import create_access_token
from app.security.passwords import hash_password, verify_password


class AuthService:
    # Handles user registration and login.

    def __init__(self, user_repository: UserRepository, settings: Settings) -> None:
        # Initialize service dependencies.
        self._user_repository = user_repository
        self._settings = settings

    def register(self, email: str, password: str) -> User:
        # Register a user account.
        normalized_email = sanitize_email(email)
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="password must be at least 8 characters")
        if self._user_repository.get_by_email(normalized_email) is not None:
            raise HTTPException(status_code=409, detail="email already exists")
        user = User(
            id=str(uuid4()),
            email=normalized_email,
            password_hash=hash_password(password),
            created_at=datetime.now(timezone.utc),
        )
        return self._user_repository.create_user(user)

    def login(self, email: str, password: str) -> tuple[str, User]:
        # Validate credentials and issue access token.
        normalized_email = sanitize_email(email)
        user = self._user_repository.get_by_email(normalized_email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            secret=self._settings.jwt_secret,
            algorithm=self._settings.jwt_alg,
            expires_minutes=self._settings.jwt_expires_min,
        )
        return token, user
