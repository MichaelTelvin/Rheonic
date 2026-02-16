# Concrete incident repository implementation scaffold.
from app.application.interfaces.incident_repository import IncidentRepository
from app.domain.models.incident import Incident


class IncidentRepositoryImpl(IncidentRepository):
    # Database-backed implementation for incidents.
    def add(self, incident: Incident) -> None:
        _ = incident
        # TODO: Persist incident record.

    def list_recent(self, project_id: str, limit: int = 100) -> list[Incident]:
        _ = (project_id, limit)
        # TODO: Query recent incidents.
        return []
