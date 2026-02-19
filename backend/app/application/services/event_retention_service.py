# Application service for raw event retention and purging.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.application.interfaces.event_repository import EventRepository
from app.logger import get_logger

logger = get_logger(__name__)


class EventRetentionService:
    # Purges raw events older than a configured retention window.

    def __init__(self, event_repository: EventRepository, retention_days: int) -> None:
        self._event_repository = event_repository
        self._retention_days = max(int(retention_days), 1)

    def purge_old_events(self, now: datetime | None = None) -> int:
        # Delete rows older than retention window and return deleted count.
        reference_time = now or datetime.now(timezone.utc)
        cutoff = reference_time - timedelta(days=self._retention_days)
        deleted = self._event_repository.purge_older_than(cutoff=cutoff)
        logger.info(
            "Event retention purge completed",
            extra={
                "retention_days": self._retention_days,
                "cutoff": cutoff.isoformat(),
                "deleted_count": deleted,
            },
        )
        return deleted
