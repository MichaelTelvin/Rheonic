# Dependency wiring for API routes.
from functools import lru_cache

from fastapi import HTTPException, Request

from app.application.services.auth_service import AuthService
from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.incident_manager import IncidentManager
from app.application.services.ingest_event_service import IngestEventService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.metrics_service import MetricsService
from app.application.services.project_service import ProjectService
from app.application.services.protect_service import ProtectService
from app.application.services.transport_service import TransportService
from app.config import Settings
from app.domain.models.user import User
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.refresh_session_repository_impl import RefreshSessionRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.infrastructure.db.repositories.user_repository_impl import UserRepositoryImpl
from app.infrastructure.jobs.transport_job import enqueue_outbox_delivery
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.redis_client import RedisClient
from app.infrastructure.redis.rolling_window import RollingWindow
from app.logger import get_logger
from app.security.jwt_tokens import decode_access_token

logger = get_logger(__name__)


@lru_cache
def get_db_session_factory() -> DatabaseSessionFactory:
    # Provide a shared database session factory.
    try:
        return DatabaseSessionFactory()
    except Exception:
        logger.exception("Failed to initialize database session factory")
        raise


@lru_cache
def get_redis_client() -> RedisClient:
    # Provide a shared Redis client.
    try:
        return RedisClient()
    except Exception:
        logger.exception("Failed to initialize Redis client")
        raise


@lru_cache
def get_rolling_window() -> RollingWindow:
    # Provide a shared Redis rolling window adapter.
    try:
        return RollingWindow(client=get_redis_client())
    except Exception:
        logger.exception("Failed to initialize rolling window adapter")
        raise


@lru_cache
def get_protect_action_store() -> ProtectActionStore:
    # Provide a shared Redis protect action counter adapter.
    try:
        return ProtectActionStore(redis_client=get_redis_client())
    except Exception:
        logger.exception("Failed to initialize protect action store")
        raise


@lru_cache
def get_settings() -> Settings:
    # Provide runtime settings.
    try:
        return Settings()
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
        return IngestEventService(
            event_repository=EventRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            retry_storm_window_seconds=get_settings().retry_storm_window_seconds,
            retry_storm_count=get_settings().retry_storm_count,
            loop_window_seconds=get_settings().loop_window_seconds,
            loop_count=get_settings().loop_count,
            loop_max_gap_seconds=get_settings().loop_max_gap_seconds,
            loop_concurrency_threshold=get_settings().loop_concurrency_threshold,
            token_explosion_ratio=get_settings().token_explosion_ratio,
            token_explosion_abs=get_settings().token_explosion_abs,
            token_explosion_growth_ratio=get_settings().token_explosion_growth_ratio,
            token_explosion_growth_count=get_settings().token_explosion_growth_count,
            token_explosion_growth_min_tokens=get_settings().token_explosion_growth_min_tokens,
            token_explosion_concurrency_threshold=get_settings().token_explosion_concurrency_threshold,
            webhook_dispatcher=get_webhook_dispatcher(),
            transport_service=get_transport_service(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
    except Exception:
        logger.exception("Failed to construct ingest event service")
        raise


def get_metrics_service() -> MetricsService:
    # Provide a metrics service instance.
    try:
        return MetricsService(
            realtime_counters=get_rolling_window(),
            protect_action_store=get_protect_action_store(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
            transport_outbox_repository=TransportOutboxRepositoryImpl(session_factory=get_db_session_factory()),
        )
    except Exception:
        logger.exception("Failed to construct metrics service")
        raise


def get_detect_incidents_service() -> DetectIncidentsService:
    # Provide an incident detection service instance.
    try:
        return DetectIncidentsService(
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            webhook_dispatcher=get_webhook_dispatcher(),
            transport_service=get_transport_service(),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
    except Exception:
        logger.exception("Failed to construct detect incidents service")
        raise


def get_incident_manager() -> IncidentManager:
    # Provide the shared incident upsert manager used by ingest and protect block recording.
    try:
        return IncidentManager(
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            webhook_dispatcher=get_webhook_dispatcher(),
            transport_service=get_transport_service(),
        )
    except Exception:
        logger.exception("Failed to construct incident manager")
        raise


def get_project_service() -> ProjectService:
    # Provide a project service instance.
    try:
        return ProjectService(
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
    except Exception:
        logger.exception("Failed to construct project service")
        raise


def get_ingest_key_service() -> IngestKeyService:
    # Provide an ingest key service instance.
    try:
        return IngestKeyService(
            ingest_key_repository=IngestKeyRepositoryImpl(session_factory=get_db_session_factory()),
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
        )
    except Exception:
        logger.exception("Failed to construct ingest key service")
        raise


def get_protect_service() -> ProtectService:
    # Provide protect decision service.
    try:
        return ProtectService(
            ingest_key_service=get_ingest_key_service(),
            realtime_counters=get_rolling_window(),
            protect_action_store=get_protect_action_store(),
            protect_block_cooldown_seconds=get_settings().protect_block_cooldown_seconds,
            project_repository=ProjectRepositoryImpl(session_factory=get_db_session_factory()),
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            protect_decision_timeout_ms=get_settings().protect_decision_timeout_ms,
            protect_clamp_factor=get_settings().protect_clamp_factor,
            webhook_dispatcher=get_webhook_dispatcher(),
            transport_service=get_transport_service(),
        )
    except Exception:
        logger.exception("Failed to construct protect service")
        raise


def get_auth_service() -> AuthService:
    # Provide an auth service instance.
    try:
        return AuthService(
            user_repository=UserRepositoryImpl(session_factory=get_db_session_factory()),
            refresh_session_repository=RefreshSessionRepositoryImpl(session_factory=get_db_session_factory()),
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
