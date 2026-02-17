# Concrete ingest key repository implementation.
from datetime import datetime

from app.application.interfaces.ingest_key_repository import IngestKeyRepository
from app.domain.models.ingest_key import IngestKey
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import IngestKeyRecord
from app.logger import get_logger

logger = get_logger(__name__)


class IngestKeyRepositoryImpl(IngestKeyRepository):
    # Database-backed implementation for ingest key persistence.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory

    def list_by_project(self, project_id: str) -> list[IngestKey]:
        # Return keys for a project ordered by creation descending.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(IngestKeyRecord)
                    .filter(IngestKeyRecord.project_id == project_id)
                    .order_by(IngestKeyRecord.created_at.desc())
                    .all()
                )
            return [_to_domain(record) for record in records]
        except Exception:
            logger.exception("Failed listing ingest keys", extra={"project_id": project_id})
            raise

    def get_by_id(self, key_id: str) -> IngestKey | None:
        # Return one key by id.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(IngestKeyRecord).filter(IngestKeyRecord.id == key_id).first()
            return _to_domain(record) if record is not None else None
        except Exception:
            logger.exception("Failed fetching ingest key by id", extra={"key_id": key_id})
            raise

    def get_active_by_hash(self, key_hash: str) -> IngestKey | None:
        # Return active key matching hash.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(IngestKeyRecord)
                    .filter(IngestKeyRecord.key_hash == key_hash, IngestKeyRecord.status == "active")
                    .first()
                )
            return _to_domain(record) if record is not None else None
        except Exception:
            logger.exception("Failed fetching active ingest key by hash")
            raise

    def create_key(self, key: IngestKey) -> IngestKey:
        # Persist new ingest key row.
        try:
            with self._session_factory.create_session() as session:
                session.add(
                    IngestKeyRecord(
                        id=key.id,
                        project_id=key.project_id,
                        name=key.name,
                        key_hash=key.key_hash,
                        last4=key.last4,
                        status=key.status,
                        created_at=key.created_at,
                        revoked_at=key.revoked_at,
                    )
                )
                session.commit()
            return key
        except Exception:
            logger.exception("Failed creating ingest key", extra={"project_id": key.project_id})
            raise

    def revoke_key(self, key_id: str, revoked_at: datetime) -> IngestKey | None:
        # Mark key as revoked if found.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(IngestKeyRecord).filter(IngestKeyRecord.id == key_id).first()
                if record is None:
                    return None
                record.status = "revoked"
                record.revoked_at = revoked_at
                session.commit()
            return _to_domain(record)
        except Exception:
            logger.exception("Failed revoking ingest key", extra={"key_id": key_id})
            raise


def _to_domain(record: IngestKeyRecord) -> IngestKey:
    # Convert SQLAlchemy ingest key record to domain model.
    return IngestKey(
        id=record.id,
        project_id=record.project_id,
        name=record.name,
        key_hash=record.key_hash,
        last4=record.last4,
        status=record.status,
        created_at=record.created_at,
        revoked_at=record.revoked_at,
    )
