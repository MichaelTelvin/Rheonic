# Dependency wiring for API routes.
from functools import lru_cache

from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.ingest_event_service import IngestEventService
from app.application.services.metrics_service import MetricsService
from app.application.services.project_service import ProjectService
from app.config import Settings
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.redis_client import RedisClient
from app.infrastructure.redis.rolling_window import RollingWindow
from app.logger import get_logger

logger = get_logger(__name__)


@lru_cache
def get_db_session_factory() -> DatabaseSessionFactory:
    # Provide a shared database session factory.
    try:
        session_factory = DatabaseSessionFactory()
        Base.metadata.create_all(bind=session_factory.engine)
        logger.info("Database session factory initialized")
        return session_factory
    except Exception:
        logger.exception("Failed to initialize database session factory")
        raise


@lru_cache
def get_redis_client() -> RedisClient:
    # Provide a shared Redis client.
    try:
        client = RedisClient()
        logger.info("Redis client initialized")
        return client
    except Exception:
        logger.exception("Failed to initialize Redis client")
        raise


@lru_cache
def get_rolling_window() -> RollingWindow:
    # Provide a shared Redis rolling window adapter.
    try:
        adapter = RollingWindow(client=get_redis_client())
        logger.debug("Rolling window adapter initialized")
        return adapter
    except Exception:
        logger.exception("Failed to initialize rolling window adapter")
        raise


@lru_cache
def get_settings() -> Settings:
    # Provide runtime settings.
    try:
        settings = Settings()
        logger.debug("Settings initialized")
        return settings
    except Exception:
        logger.exception("Failed to initialize settings")
        raise


def get_ingest_event_service() -> IngestEventService:
    # Provide an ingest event service instance.
    try:
        service = IngestEventService(
            event_repository=EventRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            threshold_tokens_60s=get_settings().threshold_tokens_60s,
            threshold_req_60s=get_settings().threshold_req_60s,
            incident_lock_ttl_seconds=get_settings().incident_lock_ttl_seconds,
        )
        logger.debug("Ingest event service provided")
        return service
    except Exception:
        logger.exception("Failed to construct ingest event service")
        raise


def get_metrics_service() -> MetricsService:
    # Provide a metrics service instance.
    try:
        service = MetricsService(realtime_counters=get_rolling_window())
        logger.debug("Metrics service provided")
        return service
    except Exception:
        logger.exception("Failed to construct metrics service")
        raise


def get_detect_incidents_service() -> DetectIncidentsService:
    # Provide an incident detection service instance.
    # TODO: Inject detector and repository dependencies.
    try:
        service = DetectIncidentsService(
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
        )
        logger.debug("Detect incidents service provided")
        return service
    except Exception:
        logger.exception("Failed to construct detect incidents service")
        raise


def get_project_service() -> ProjectService:
    # Provide a project service instance.
    try:
        service = ProjectService(
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
        logger.debug("Project service provided")
        return service
    except Exception:
        logger.exception("Failed to construct project service")
        raise


def get_ingest_key_service() -> IngestKeyService:
    # Provide an ingest key service instance.
    try:
        service = IngestKeyService(
            ingest_key_repository=IngestKeyRepositoryImpl(session_factory=get_db_session_factory()),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
        logger.debug("Ingest key service provided")
        return service
    except Exception:
        logger.exception("Failed to construct ingest key service")
        raise
