# Event repository interface.
from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.models.event import Event


class EventRepository(ABC):
    # Abstraction for event persistence and retrieval.

    @abstractmethod
    def add(self, event: Event) -> None:
        # Persist a new event.
        raise NotImplementedError

    @abstractmethod
    def list_recent(self, project_id: str, limit: int = 100, provider: str | None = None) -> list[Event]:
        # Return the most recent events for a project.
        raise NotImplementedError

    @abstractmethod
    def purge_older_than(self, cutoff: datetime) -> int:
        # Delete events older than cutoff and return deleted row count.
        raise NotImplementedError
