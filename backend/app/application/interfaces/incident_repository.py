# Incident repository interface.
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.incident import Incident


class IncidentRepository(ABC):
    # Abstraction for incident persistence and retrieval.

    @abstractmethod
    def create_incident(self, incident: Incident) -> Incident:
        # Persist and return a new incident record.
        raise NotImplementedError

    @abstractmethod
    def get_open_incident_by_type(self, project_id: str, provider: str, incident_type: str) -> Incident | None:
        # Return an open incident for a project/type if one exists.
        raise NotImplementedError

    @abstractmethod
    def get_open_incident_by_fingerprint(
        self,
        project_id: str,
        provider: str,
        fingerprint: str,
        created_after: datetime,
    ) -> Incident | None:
        # Return an open incident for a project/fingerprint created after timestamp.
        raise NotImplementedError

    @abstractmethod
    def update_open_incident_activity(
        self,
        incident_id: str,
        evidence: dict[str, object],
        last_seen_at: datetime,
    ) -> Incident | None:
        # Update deduped incident evidence/last_seen and return updated row.
        raise NotImplementedError

    @abstractmethod
    def list_by_project(
        self,
        project_id: str,
        status: str = "open",
        provider: str | None = None,
    ) -> list[Incident]:
        # Return incidents for project filtered by status.
        raise NotImplementedError

    @abstractmethod
    def list_open_by_project_provider(self, project_id: str, provider: str) -> list[Incident]:
        # Return open incidents for project/provider.
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, incident_id: str) -> Incident | None:
        # Return incident by id.
        raise NotImplementedError

    @abstractmethod
    def resolve_incident(self, incident_id: str) -> Incident | None:
        # Mark incident as resolved and return updated incident.
        raise NotImplementedError

    @abstractmethod
    def resolve_open_incidents_by_type(
        self,
        *,
        project_id: str,
        provider: str,
        incident_type: str,
        resolved_at: datetime,
    ) -> list[Incident]:
        # Resolve open incidents for a project/provider/type and return changed rows.
        raise NotImplementedError

    @abstractmethod
    def auto_resolve_stale_open_incidents(
        self,
        *,
        cutoff: datetime,
        resolved_at: datetime,
    ) -> tuple[list[Incident], set[tuple[str, str]]]:
        # Auto-resolve stale open incidents and return (resolved_incidents, affected project/provider pairs).
        raise NotImplementedError
