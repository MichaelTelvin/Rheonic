# Concrete incident repository implementation scaffold.
from datetime import datetime, timezone

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
                    type=incident.incident_type,
                    severity=incident.severity,
                    status=incident.status,
                    evidence=incident.evidence,
                    created_at=incident.created_at,
                    resolved_at=incident.resolved_at,
                )
                session.add(record)
                session.commit()
            logger.info("Incident created", extra={"project_id": incident.project_id, "incident_id": incident.id})
            return incident
        except Exception:
            logger.exception("Failed creating incident", extra={"project_id": incident.project_id})
            raise

    def get_open_incident_by_type(self, project_id: str, incident_type: str) -> Incident | None:
        # Return open incident for project and type.
        try:
            with self._session_factory.create_session() as session:
                record = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.type == incident_type)
                    .filter(IncidentRecord.status == "open")
                    .order_by(IncidentRecord.created_at.desc())
                    .first()
                )
            if record is None:
                return None
            return _to_domain(record)
        except Exception:
            logger.exception("Failed fetching open incident", extra={"project_id": project_id, "incident_type": incident_type})
            raise

    def list_by_project(self, project_id: str, status: str = "open") -> list[Incident]:
        # List incidents by project and status.
        try:
            with self._session_factory.create_session() as session:
                records = (
                    session.query(IncidentRecord)
                    .filter(IncidentRecord.project_id == project_id)
                    .filter(IncidentRecord.status == status)
                    .order_by(IncidentRecord.created_at.desc())
                    .all()
                )
            return [_to_domain(record) for record in records]
        except Exception:
            logger.exception("Failed listing incidents", extra={"project_id": project_id, "status": status})
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


def _to_domain(record: IncidentRecord) -> Incident:
    # Convert SQLAlchemy incident record to domain model.
    return Incident(
        id=record.id,
        project_id=record.project_id,
        incident_type=record.type,
        severity=record.severity,
        status=record.status,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
        evidence=record.evidence,
    )
