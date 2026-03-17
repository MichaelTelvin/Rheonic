from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.application.interfaces.transport_outbox_repository import TransportOutboxRepository
from app.domain.models.transport_outbox import TransportOutbox
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import TransportOutboxRecord
from app.logger import get_logger

logger = get_logger(__name__)


class TransportOutboxRepositoryImpl(TransportOutboxRepository):
    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        self._session_factory = session_factory

    def create_or_get_deduped(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        event_type: str,
        destination: str | None,
        subject: str | None,
        template: str | None,
        payload: dict[str, object],
        dedupe_key: str,
        max_attempts: int,
        now: datetime,
    ) -> tuple[TransportOutbox, bool]:
        try:
            with self._session_factory.create_session() as session:
                record = TransportOutboxRecord(
                    id=_id(now),
                    project_id=project_id,
                    kind=kind,
                    event_type=event_type,
                    destination=destination,
                    subject=subject,
                    template=template,
                    payload=payload,
                    dedupe_key=dedupe_key,
                    status="pending",
                    attempts=0,
                    max_attempts=max_attempts,
                    next_attempt_at=now,
                    last_error_code=None,
                    last_error_message=None,
                    created_at=now,
                    updated_at=now,
                    sent_at=None,
                    delivered_at=None,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                return _to_domain(record), True
        except IntegrityError:
            with self._session_factory.create_session() as session:
                existing = (
                    session.query(TransportOutboxRecord)
                    .filter(TransportOutboxRecord.project_id == project_id)
                    .filter(TransportOutboxRecord.kind == kind)
                    .filter(TransportOutboxRecord.dedupe_key == dedupe_key)
                    .first()
                )
                if existing is None:
                    raise
                return _to_domain(existing), False
        except Exception:
            logger.exception(
                "Failed creating outbox row",
                extra={"project_id": project_id, "kind": kind, "event_type": event_type},
            )
            raise

    def claim_for_send(self, *, outbox_id: str, now: datetime) -> TransportOutbox | None:
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(TransportOutboxRecord)
                    .filter(TransportOutboxRecord.id == outbox_id)
                    .filter(TransportOutboxRecord.status.in_(["pending", "failed"]))
                    .filter(TransportOutboxRecord.next_attempt_at <= now)
                    .first()
                )
                if record is None:
                    return None
                record.status = "sending"
                record.attempts = int(record.attempts) + 1
                record.updated_at = now
                record.sent_at = now
                session.add(record)
                session.commit()
                session.refresh(record)
                return _to_domain(record)
        except Exception:
            logger.exception("Failed claiming outbox row", extra={"outbox_id": outbox_id})
            raise

    def mark_delivered(self, *, outbox_id: str, now: datetime) -> TransportOutbox | None:
        try:
            with self._session_factory.create_session() as session:
                record = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
                if record is None:
                    return None
                record.status = "delivered"
                record.updated_at = now
                record.delivered_at = now
                record.last_error_code = None
                record.last_error_message = None
                session.add(record)
                session.commit()
                session.refresh(record)
                return _to_domain(record)
        except Exception:
            logger.exception("Failed marking outbox delivered", extra={"outbox_id": outbox_id})
            raise

    def mark_failed(
        self,
        *,
        outbox_id: str,
        now: datetime,
        error_code: str,
        error_message: str,
        next_attempt_at: datetime | None,
        dead: bool,
    ) -> TransportOutbox | None:
        try:
            with self._session_factory.create_session() as session:
                record = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
                if record is None:
                    return None
                record.status = "dead" if dead else "failed"
                record.updated_at = now
                record.next_attempt_at = next_attempt_at or now
                record.last_error_code = error_code
                record.last_error_message = error_message[:512]
                session.add(record)
                session.commit()
                session.refresh(record)
                return _to_domain(record)
        except Exception:
            logger.exception("Failed marking outbox failed", extra={"outbox_id": outbox_id})
            raise

    def get_by_id(self, outbox_id: str) -> TransportOutbox | None:
        try:
            with self._session_factory.create_session() as session:
                record = session.query(TransportOutboxRecord).filter(TransportOutboxRecord.id == outbox_id).first()
                if record is None:
                    return None
                return _to_domain(record)
        except Exception:
            logger.exception("Failed fetching outbox row", extra={"outbox_id": outbox_id})
            raise

    def get_latest_terminal_by_project_kind(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        exclude_event_types: tuple[str, ...] = (),
        since: datetime | None = None,
    ) -> TransportOutbox | None:
        try:
            with self._session_factory.create_session() as session:
                query = (
                    session.query(TransportOutboxRecord)
                    .filter(TransportOutboxRecord.project_id == project_id)
                    .filter(TransportOutboxRecord.kind == kind)
                    .filter(TransportOutboxRecord.status.in_(["delivered", "failed", "dead"]))
                )
                if exclude_event_types:
                    query = query.filter(~TransportOutboxRecord.event_type.in_(exclude_event_types))
                if since is not None:
                    query = query.filter(TransportOutboxRecord.updated_at >= since)
                record = query.order_by(TransportOutboxRecord.updated_at.desc()).first()
                if record is None:
                    return None
                return _to_domain(record)
        except Exception:
            logger.exception(
                "Failed fetching latest terminal outbox",
                extra={"project_id": project_id, "kind": kind},
            )
            raise

    def count_failed_or_dead_by_project_kind(
        self,
        *,
        project_id: str,
        kind: Literal["webhook", "email"],
        exclude_event_types: tuple[str, ...] = (),
        since: datetime | None = None,
    ) -> int:
        try:
            with self._session_factory.create_session() as session:
                query = (
                    session.query(TransportOutboxRecord)
                    .filter(TransportOutboxRecord.project_id == project_id)
                    .filter(TransportOutboxRecord.kind == kind)
                    .filter(TransportOutboxRecord.status.in_(["failed", "dead"]))
                )
                if exclude_event_types:
                    query = query.filter(~TransportOutboxRecord.event_type.in_(exclude_event_types))
                if since is not None:
                    query = query.filter(TransportOutboxRecord.updated_at >= since)
                return int(query.count())
        except Exception:
            logger.exception(
                "Failed counting failed/dead outbox rows",
                extra={"project_id": project_id, "kind": kind},
            )
            raise


def _id(now: datetime) -> str:
    _ = now
    return str(uuid4())


def _to_domain(record: TransportOutboxRecord) -> TransportOutbox:
    return TransportOutbox(
        id=record.id,
        project_id=record.project_id,
        kind=record.kind,  # type: ignore[arg-type]
        event_type=record.event_type,
        destination=record.destination,
        subject=record.subject,
        template=record.template,
        payload=record.payload,
        dedupe_key=record.dedupe_key,
        status=record.status,  # type: ignore[arg-type]
        attempts=int(record.attempts),
        max_attempts=int(record.max_attempts),
        next_attempt_at=record.next_attempt_at,
        last_error_code=record.last_error_code,
        last_error_message=record.last_error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
        sent_at=record.sent_at,
        delivered_at=record.delivered_at,
    )
