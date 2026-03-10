# Concrete incident repository implementation scaffold.
from datetime import datetime, timezone

from sqlalchemy import and_, or_

from app.application.interfaces.incident_repository import IncidentRepository
from app.domain.models.incident import Incident
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import IncidentRecord
from app.logger import get_logger

logger = get_logger(__name__)


class IncidentRepositoryImpl(IncidentRepository):
    # Database-backed implementation for incidents.

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        # Initialize repository dependencies.
        self._session_factory = session_factory

    def create_incident(self, incident: Incident) -> Incident:
        # Persist and return a new incident.
        try:
            with self._session_factory.create_session() as session:
                record = IncidentRecord(
                    id=incident.id,
                    project_id=incident.project_id,
                    provider=incident.provider,
                    type=incident.incident_type,
                    status=incident.status,
                    fingerprint=incident.fingerprint,
                    evidence=incident.evidence,
                    created_at=incident.created_at,
                    resolved_at=incident.resolved_at,
                    last_seen_at=incident.last_seen_at,
                )
                session.add(record)
                session.commit()
            logger.info("Incident created", extra={"project_id": incident.project_id, "incident_id": incident.id})
            return incident
        except Exception:
            logger.exception("Failed creating incident", extra={"project_id": incident.project_id})
            raise

    def get_open_incident_by_type(self, project_id: str, provider: str, incident_type: str) -> Incident | None:
        # Return open incident for project and type.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.provider == provider)
                    .filter(IncidentRecord.type == incident_type)
                    .filter(IncidentRecord.status == "open")
                    .order_by(IncidentRecord.created_at.desc())
                    .first()
                )
            if record is None:
                return None
            return _to_domain(record)
        except Exception:
            logger.exception(
                "Failed fetching open incident",
                extra={"project_id": project_id, "provider": provider, "incident_type": incident_type},
            )
            raise

    def get_open_incident_by_fingerprint(
        self,
        project_id: str,
        provider: str,
        fingerprint: str,
        created_after: datetime,
    ) -> Incident | None:
        # Return open incident by fingerprint created within dedup window.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.provider == provider)
                    .filter(IncidentRecord.status == "open")
                    .filter(IncidentRecord.fingerprint == fingerprint)
                    .filter(IncidentRecord.created_at >= created_after)
                    .order_by(IncidentRecord.created_at.desc())
                    .first()
                )
            if record is None:
                return None
            return _to_domain(record)
        except Exception:
            logger.exception(
                "Failed fetching open incident by fingerprint",
                extra={"project_id": project_id, "provider": provider, "fingerprint": fingerprint},
            )
            raise

    def update_open_incident_activity(
        self,
        incident_id: str,
        evidence: dict[str, object],
        last_seen_at: datetime,
    ) -> Incident | None:
        # Update dedup activity fields for an existing open incident.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.id == incident_id)
                    .filter(IncidentRecord.status == "open")
                    .first()
                )
                if record is None:
                    return None
                record.evidence = evidence
                record.last_seen_at = last_seen_at
                session.add(record)
                session.commit()
                session.refresh(record)
            return _to_domain(record)
        except Exception:
            logger.exception("Failed updating open incident activity", extra={"incident_id": incident_id})
            raise

    def list_by_project(
        self,
        project_id: str,
        status: str = "open",
        provider: str | None = None,
    ) -> list[Incident]:
        # List incidents by project and status.
        try:
            with self._session_factory.create_session() as session:
                query = session.query(IncidentRecord).filter(IncidentRecord.project_id == project_id)
                if status and status != "all":
                    if status == "resolved":
                        query = query.filter(IncidentRecord.status.in_(["resolved", "auto_resolved"]))
                    else:
                        query = query.filter(IncidentRecord.status == status)
                if provider:
                    query = query.filter(IncidentRecord.provider == provider)
                records = query.order_by(IncidentRecord.created_at.desc()).all()
            return [_to_domain(record) for record in records]
        except Exception:
            logger.exception(
                "Failed listing incidents",
                extra={"project_id": project_id, "status": status, "provider": provider},
            )
            raise

    def list_open_by_project_provider(self, project_id: str, provider: str) -> list[Incident]:
        # List open incidents by project/provider.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.provider == provider)
                    .filter(IncidentRecord.status == "open")
                    .order_by(IncidentRecord.created_at.desc())
                    .all()
                )
            return [_to_domain(record) for record in records]
        except Exception:
            logger.exception("Failed listing open incidents by provider", extra={"project_id": project_id, "provider": provider})
            raise

    def get_by_id(self, incident_id: str) -> Incident | None:
        # Fetch incident by id.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(IncidentRecord).filter(IncidentRecord.id == incident_id).first()
            if record is None:
                return None
            return _to_domain(record)
        except Exception:
            logger.exception("Failed fetching incident by id", extra={"incident_id": incident_id})
            raise

    def resolve_incident(self, incident_id: str) -> Incident | None:
        # Mark incident resolved.
        try:
            with self._session_factory.create_session() as session:
                record = session.query(IncidentRecord).filter(IncidentRecord.id == incident_id).first()
                if record is None:
                    return None
                record.status = "resolved"
                record.resolved_at = datetime.now(timezone.utc)
                session.add(record)
                session.commit()
                session.refresh(record)
            logger.info("Incident resolved", extra={"incident_id": incident_id})
            return _to_domain(record)
        except Exception:
            logger.exception("Failed resolving incident", extra={"incident_id": incident_id})
            raise

    def resolve_open_incidents_by_type(
        self,
        *,
        project_id: str,
        provider: str,
        incident_type: str,
        resolved_at: datetime,
    ) -> list[Incident]:
        # Resolve all open incidents for the same project/provider/type.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.provider == provider)
                    .filter(IncidentRecord.type == incident_type)
                    .filter(IncidentRecord.status == "open")
                    .all()
                )
                if not records:
                    return []
                for record in records:
                    record.status = "resolved"
                    record.resolved_at = resolved_at
                    session.add(record)
                session.commit()
                resolved = [_to_domain(record) for record in records]
            logger.info(
                "Open incidents resolved by type",
                extra={"project_id": project_id, "provider": provider, "incident_type": incident_type, "count": len(resolved)},
            )
            return resolved
        except Exception:
            logger.exception(
                "Failed resolving open incidents by type",
                extra={"project_id": project_id, "provider": provider, "incident_type": incident_type},
            )
            raise

    def auto_resolve_stale_open_incidents(
        self,
        *,
        cutoff: datetime,
        resolved_at: datetime,
    ) -> tuple[list[Incident], set[tuple[str, str]]]:
        # Mark stale open incidents as auto_resolved.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.status == "open")
                    .filter(
                        or_(
                            IncidentRecord.last_seen_at < cutoff,
                            and_(IncidentRecord.last_seen_at.is_(None), IncidentRecord.created_at < cutoff),
                        )
                    )
                    .all()
                )
                if not records:
                    return [], set()
                project_provider_pairs = {(record.project_id, record.provider) for record in records}
                for record in records:
                    record.status = "auto_resolved"
                    record.resolved_at = resolved_at
                    session.add(record)
                session.commit()
                resolved_incidents = [_to_domain(record) for record in records]
            logger.info("Stale incidents auto-resolved", extra={"count": len(records)})
            return resolved_incidents, project_provider_pairs
        except Exception:
            logger.exception("Failed auto-resolving stale incidents")
            raise


def _to_domain(record: IncidentRecord) -> Incident:
    # Convert SQLAlchemy incident record to domain model.
    return Incident(
        id=record.id,
        project_id=record.project_id,
        provider=record.provider or "unknown",
        incident_type=record.type,
        status=record.status,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
        evidence=record.evidence,
        fingerprint=record.fingerprint,
        last_seen_at=record.last_seen_at,
    )
