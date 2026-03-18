# Refresh session repository implementation.
from datetime import datetime, timezone

from app.application.interfaces.refresh_session_repository import RefreshSessionRepository
from app.domain.models.refresh_session import RefreshSession
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import RefreshSessionRecord
from app.logger import get_logger

logger = get_logger(__name__)


class RefreshSessionRepositoryImpl(RefreshSessionRepository):
    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        self._session_factory = session_factory

    def create_session(self, session: RefreshSession) -> RefreshSession:
        try:
            with self._session_factory.create_session() as db_session:
                db_session.add(
                    RefreshSessionRecord(
                        jti=session.jti,
                        user_id=session.user_id,
                        created_at=session.created_at,
                        expires_at=session.expires_at,
                        revoked_at=session.revoked_at,
                        replaced_by_jti=session.replaced_by_jti,
                    )
                )
                db_session.commit()
            return session
        except Exception:
            logger.exception("Failed creating refresh session")
            raise

    def get_by_jti(self, jti: str) -> RefreshSession | None:
        try:
            with self._session_factory.create_session() as db_session:
                record = db_session.query(RefreshSessionRecord).filter(RefreshSessionRecord.jti == jti).first()
            return _to_domain(record) if record is not None else None
        except Exception:
            logger.exception("Failed fetching refresh session", extra={"jti": jti})
            raise

    def rotate_session(self, *, current_jti: str, replacement: RefreshSession, revoked_at: datetime) -> bool:
        try:
            with self._session_factory.create_session() as db_session:
                updated = (
                    db_session.query(RefreshSessionRecord)
                    .filter(
                        RefreshSessionRecord.jti == current_jti,
                        RefreshSessionRecord.revoked_at.is_(None),
                        RefreshSessionRecord.expires_at > datetime.now(timezone.utc),
                    )
                    .update(
                        {
                            RefreshSessionRecord.revoked_at: revoked_at,
                            RefreshSessionRecord.replaced_by_jti: replacement.jti,
                        },
                        synchronize_session=False,
                    )
                )
                if updated != 1:
                    db_session.rollback()
                    return False
                db_session.add(
                    RefreshSessionRecord(
                        jti=replacement.jti,
                        user_id=replacement.user_id,
                        created_at=replacement.created_at,
                        expires_at=replacement.expires_at,
                        revoked_at=replacement.revoked_at,
                        replaced_by_jti=replacement.replaced_by_jti,
                    )
                )
                db_session.commit()
                return True
        except Exception:
            logger.exception("Failed rotating refresh session", extra={"jti": current_jti})
            raise

    def revoke_session(self, *, jti: str, revoked_at: datetime) -> bool:
        try:
            with self._session_factory.create_session() as db_session:
                updated = (
                    db_session.query(RefreshSessionRecord)
                    .filter(
                        RefreshSessionRecord.jti == jti,
                        RefreshSessionRecord.revoked_at.is_(None),
                    )
                    .update(
                        {RefreshSessionRecord.revoked_at: revoked_at},
                        synchronize_session=False,
                    )
                )
                db_session.commit()
                return updated == 1
        except Exception:
            logger.exception("Failed revoking refresh session", extra={"jti": jti})
            raise


def _to_domain(record: RefreshSessionRecord) -> RefreshSession:
    return RefreshSession(
        jti=record.jti,
        user_id=record.user_id,
        created_at=record.created_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        replaced_by_jti=record.replaced_by_jti,
    )
