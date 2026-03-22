# Background job for auto-closing stale incidents.
from __future__ import annotations

from app.application.services.auto_close_incidents_service import AutoCloseIncidentsService
from app.application.services.transport_service import TransportService
from app.config import Settings
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.jobs.transport_job import enqueue_outbox_delivery
from app.logger import get_logger

logger = get_logger(__name__)


def auto_close_incidents() -> int:
    # Auto-close incidents that have not been seen within cooldown.
    try:
        settings = Settings()
        session_factory = DatabaseSessionFactory(database_url=settings.database_url)
        repository = IncidentRepositoryImpl(session_factory=session_factory)
        service = AutoCloseIncidentsService(
            incident_repository=repository,
            cooldown_seconds=settings.incident_auto_close_seconds,
            webhook_dispatcher=RQWebhookDispatcher(redis_url=settings.redis_url),
            transport_service=TransportService(
                outbox_repository=TransportOutboxRepositoryImpl(session_factory=session_factory),
                enqueue_job=enqueue_outbox_delivery,
            ),
            project_repository=ProjectRepositoryImpl(session_factory=session_factory),
        )
        return service.auto_close()
    except Exception:
        logger.exception("Auto-close incidents job failed")
        raise
