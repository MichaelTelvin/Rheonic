# Concrete event repository implementation scaffold.
from datetime import datetime

from app.application.interfaces.event_repository import EventRepository
from app.domain.models.event import Event
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import EventRecord
from app.logger import get_logger

logger = get_logger(__name__)


class EventRepositoryImpl(EventRepository):
    # Database-backed implementation for event persistence.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory

    def add(self, event: Event) -> None:
        # Persist a domain event record.
        try:
            with self._session_factory.create_session() as session:
                record = EventRecord(
                    id=event.id,
                    ts=event.ts,
                    project_id=event.project_id,
                    provider=event.provider,
                    model=event.model,
                    environment=event.environment,
                    input_tokens=event.input_tokens,
                    output_tokens=event.output_tokens,
                    total_tokens=event.total_tokens,
                    latency_ms=event.latency_ms,
                    status=event.status,
                    error_type=event.error_type,
                    http_status=event.http_status,
                    request_endpoint=event.request_endpoint,
                    request_feature=event.request_feature,
                    created_at=event.created_at,
                )
                session.add(record)
                session.commit()
        except Exception:
            logger.exception("Failed to persist event", extra={"project_id": event.project_id})
            raise

    def list_recent(self, project_id: str, limit: int = 100, provider: str | None = None) -> list[Event]:
        # Fetch recent events for a project.
        try:
            with self._session_factory.create_session() as session:
                query = session.query(EventRecord).filter(EventRecord.project_id == project_id)
                if provider:
                    query = query.filter(EventRecord.provider == provider)
                records = query.order_by(EventRecord.ts.desc()).limit(limit).all()
            return [
                Event(
                    id=record.id,
                    ts=record.ts,
                    project_id=record.project_id,
                    provider=record.provider,
                    model=record.model,
                    environment=record.environment,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    total_tokens=record.total_tokens,
                    latency_ms=record.latency_ms,
                    status=record.status,
                    error_type=record.error_type,
                    http_status=record.http_status,
                    request_endpoint=record.request_endpoint,
                    request_feature=record.request_feature,
                    created_at=record.created_at,
                )
                for record in records
            ]
        except Exception:
            logger.exception("Failed to list recent events", extra={"project_id": project_id})
            raise

    def purge_older_than(self, cutoff: datetime) -> int:
        # Delete events older than cutoff timestamp and return deleted count.
        try:
            with self._session_factory.create_session() as session:
                deleted = (
                    session.query(EventRecord)
                    .filter(EventRecord.ts < cutoff)
                    .delete(synchronize_session=False)
                )
                session.commit()
                return int(deleted or 0)
        except Exception:
            logger.exception("Failed purging old events", extra={"cutoff": cutoff.isoformat()})
            raise
