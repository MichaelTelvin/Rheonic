# Incident repository interface.
from abc import ABC, abstractmethod

from app.domain.models.incident import Incident


class IncidentRepository(ABC):
    # Abstraction for incident persistence and retrieval.

    @abstractmethod
    def create_incident(self, incident: Incident) -> Incident:
        # Persist and return a new incident record.
        raise NotImplementedError

    @abstractmethod
    def get_open_incident_by_type(self, project_id: str, incident_type: str) -> Incident | None:
        # Return an open incident for a project/type if one exists.
        raise NotImplementedError

    @abstractmethod
    def list_by_project(self, project_id: str, status: str = "open") -> list[Incident]:
        # Return incidents for project filtered by status.
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, incident_id: str) -> Incident | None:
        # Return incident by id.
        raise NotImplementedError

    @abstractmethod
    def resolve_incident(self, incident_id: str) -> Incident | None:
        # Mark incident as resolved and return updated incident.
        raise NotImplementedError
