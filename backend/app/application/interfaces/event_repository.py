"""Event repository interface."""

from abc import ABC, abstractmethod

from app.domain.models.event import Event


class EventRepository(ABC):
    """Abstraction for event persistence and retrieval."""

    @abstractmethod
    def add(self, event: Event) -> None:
        """Persist a new event."""

    @abstractmethod
    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        """Return the most recent events for a project."""
