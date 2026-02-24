# Background job for auto-closing stale incidents.
from __future__ import annotations

from app.application.services.auto_close_incidents_service import AutoCloseIncidentsService
from app.config import Settings
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.infrastructure.redis.redis_client import RedisClient
from app.logger import get_logger

logger = get_logger(__name__)


def auto_close_incidents() -> int:
    # Auto-close incidents that have not been seen within cooldown.
    try:
        settings = Settings()
        session_factory = DatabaseSessionFactory(database_url=settings.database_url)
        repository = IncidentRepositoryImpl(session_factory=session_factory)
        severity_cache = IncidentSeverityCache(redis_client=RedisClient(redis_url=settings.redis_url))
        service = AutoCloseIncidentsService(
            incident_repository=repository,
            incident_severity_cache=severity_cache,
            cooldown_seconds=settings.incident_auto_close_seconds,
            webhook_dispatcher=RQWebhookDispatcher(redis_url=settings.redis_url),
        )
        return service.auto_close()
    except Exception:
        logger.exception("Auto-close incidents job failed")
        raise
