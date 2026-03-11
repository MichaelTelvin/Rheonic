# Dependency wiring for API routes.
from functools import lru_cache

from fastapi import Depends, HTTPException, Request

from app.application.services.auth_service import AuthService
from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.incident_manager import IncidentManager
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.ingest_event_service import IngestEventService
from app.application.services.metrics_service import MetricsService
from app.application.services.protect_service import ProtectService
from app.application.services.project_service import ProjectService
from app.application.services.transport_service import TransportService
from app.config import Settings
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.db.repositories.user_repository_impl import UserRepositoryImpl
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.jobs.transport_job import enqueue_outbox_delivery
from app.infrastructure.redis.redis_client import RedisClient
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.rolling_window import RollingWindow
from app.logger import get_logger
from app.security.jwt_tokens import decode_access_token

logger = get_logger(__name__)
@lru_cache
def get_db_session_factory() -> DatabaseSessionFactory:
    # Provide a shared database session factory.
    try:
        session_factory = DatabaseSessionFactory()
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
def get_protect_action_store() -> ProtectActionStore:
    # Provide a shared Redis protect action counter adapter.
    try:
        adapter = ProtectActionStore(redis_client=get_redis_client())
        logger.debug("Protect action store initialized")
        return adapter
    except Exception:
        logger.exception("Failed to initialize protect action store")
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


@lru_cache
def get_webhook_dispatcher() -> RQWebhookDispatcher:
    # Provide webhook dispatcher backed by RQ queue.
    try:
        return RQWebhookDispatcher(redis_url=get_settings().redis_url)
    except Exception:
        logger.exception("Failed to initialize webhook dispatcher")
        raise


@lru_cache
def get_transport_service() -> TransportService:
    # Provide shared transport enqueue service.
    try:
        return TransportService(
            outbox_repository=TransportOutboxRepositoryImpl(session_factory=get_db_session_factory()),
            enqueue_job=enqueue_outbox_delivery,
        )
    except Exception:
        logger.exception("Failed to initialize transport service")
        raise


def get_transport_outbox_repository() -> TransportOutboxRepositoryImpl:
    # Provide transport outbox repository.
    return TransportOutboxRepositoryImpl(session_factory=get_db_session_factory())


def get_ingest_event_service() -> IngestEventService:
    # Provide an ingest event service instance.
    try:
        service = IngestEventService(
            event_repository=EventRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            retry_storm_window_seconds=get_settings().retry_storm_window_seconds,
            retry_storm_count=get_settings().retry_storm_count,
            loop_window_seconds=get_settings().loop_window_seconds,
            loop_count=get_settings().loop_count,
            token_explosion_ratio=get_settings().token_explosion_ratio,
            token_explosion_abs=get_settings().token_explosion_abs,
            webhook_dispatcher=get_webhook_dispatcher(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
        logger.debug("Ingest event service provided")
        return service
    except Exception:
        logger.exception("Failed to construct ingest event service")
        raise


def get_metrics_service() -> MetricsService:
    # Provide a metrics service instance.
    try:
        service = MetricsService(
            realtime_counters=get_rolling_window(),
            protect_action_store=get_protect_action_store(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
            transport_outbox_repository=TransportOutboxRepositoryImpl(session_factory=get_db_session_factory()),
        )
        logger.debug("Metrics service provided")
        return service
    except Exception:
        logger.exception("Failed to construct metrics service")
        raise


def get_detect_incidents_service() -> DetectIncidentsService:
    # Provide an incident detection service instance.
    try:
        service = DetectIncidentsService(
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            webhook_dispatcher=get_webhook_dispatcher(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
        logger.debug("Detect incidents service provided")
        return service
    except Exception:
        logger.exception("Failed to construct detect incidents service")
        raise


def get_incident_manager() -> IncidentManager:
    # Provide an incident upsert manager shared by ingest and preflight warning paths.
    try:
        return IncidentManager(
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            webhook_dispatcher=get_webhook_dispatcher(),
        )
    except Exception:
        logger.exception("Failed to construct incident manager")
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


def get_protect_service() -> ProtectService:
    # Provide protect decision service.
    try:
        return ProtectService(
            ingest_key_service=get_ingest_key_service(),
            event_repository=EventRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            protect_action_store=get_protect_action_store(),
            protect_block_cooldown_seconds=get_settings().protect_block_cooldown_seconds,
            webhook_dispatcher=get_webhook_dispatcher(),
        )
    except Exception:
        logger.exception("Failed to construct protect service")
        raise


def get_auth_service() -> AuthService:
    # Provide an auth service instance.
    try:
        return AuthService(
            user_repository=UserRepositoryImpl(session_factory=get_db_session_factory()),
            settings=get_settings(),
        )
    except Exception:
        logger.exception("Failed to construct auth service")
        raise


def get_current_user(request: Request) -> User:
    # Validate cookie-based access token and load user.
    access_token = request.cookies.get(get_settings().auth_access_cookie_name)
    if not access_token:
        raise HTTPException(status_code=401, detail="not authenticated")
    token_payload = decode_access_token(
        token=access_token,
        secret=get_settings().jwt_secret,
        algorithm=get_settings().jwt_alg,
    )
    if token_payload is None:
        raise HTTPException(status_code=401, detail="invalid token")
    if str(token_payload.get("typ") or "access") != "access":
        raise HTTPException(status_code=401, detail="invalid token")
    user_id = str(token_payload.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid token")
    user = UserRepositoryImpl(session_factory=get_db_session_factory()).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return user
