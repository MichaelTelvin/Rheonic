"""Concrete event repository implementation scaffold."""

from app.application.interfaces.event_repository import EventRepository
from app.domain.models.event import Event


class EventRepositoryImpl(EventRepository):
    """Database-backed implementation for event persistence."""

    def add(self, event: Event) -> None:
        _ = event
        # TODO: Persist event using ORM/session.

    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        _ = (project_id, limit)
        # TODO: Query recent events efficiently.
        return []
