# Background job for event retention purging.
from __future__ import annotations

from app.application.services.event_retention_service import EventRetentionService
from app.config import Settings
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.logger import get_logger

logger = get_logger(__name__)


def purge_old_events() -> int:
    # Purge old raw events according to configured retention period.
    try:
        settings = Settings()
        repository = EventRepositoryImpl(session_factory=DatabaseSessionFactory(database_url=settings.database_url))
        service = EventRetentionService(
            event_repository=repository,
            retention_days=settings.event_retention_days,
        )
        return service.purge_old_events()
    except Exception:
        logger.exception("Event retention purge job failed")
        raise
