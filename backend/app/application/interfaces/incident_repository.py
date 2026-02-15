"""Incident repository interface."""

from abc import ABC, abstractmethod

from app.domain.models.incident import Incident


class IncidentRepository(ABC):
    """Abstraction for incident persistence and retrieval."""

    @abstractmethod
    def add(self, incident: Incident) -> None:
        """Persist a new incident record."""

    @abstractmethod
    def list_recent(self, project_id: str, limit: int = 100) -> list[Incident]:
        """Return recent incidents for a project."""
