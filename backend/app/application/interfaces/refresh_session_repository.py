from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.refresh_session import RefreshSession


class RefreshSessionRepository(ABC):
    @abstractmethod
    def create_session(self, session: RefreshSession) -> RefreshSession:
        raise NotImplementedError

    @abstractmethod
    def get_by_jti(self, jti: str) -> RefreshSession | None:
        raise NotImplementedError

    @abstractmethod
    def rotate_session(
        self,
        *,
        current_jti: str,
        replacement: RefreshSession,
        revoked_at: datetime,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def revoke_session(self, *, jti: str, revoked_at: datetime) -> bool:
        raise NotImplementedError
