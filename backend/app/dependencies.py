# Dependency wiring for API routes.
from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import inspect, text

from app.application.services.auth_service import AuthService
from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.ingest_event_service import IngestEventService
from app.application.services.metrics_service import MetricsService
from app.application.services.protect_service import ProtectService
from app.application.services.project_service import ProjectService
from app.config import Settings
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.user_repository_impl import UserRepositoryImpl
from app.infrastructure.alerts.rq_webhook_dispatcher import RQWebhookDispatcher
from app.infrastructure.redis.redis_client import RedisClient
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.rolling_window import RollingWindow
from app.logger import get_logger
from app.security.jwt_tokens import decode_access_token

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_db_session_factory() -> DatabaseSessionFactory:
    # Provide a shared database session factory.
    try:
        session_factory = DatabaseSessionFactory()
        Base.metadata.create_all(bind=session_factory.engine)
        _ensure_legacy_schema(session_factory)
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
def get_incident_severity_cache() -> IncidentSeverityCache:
    # Provide a shared Redis incident severity cache adapter.
    try:
        adapter = IncidentSeverityCache(redis_client=get_redis_client())
        logger.debug("Incident severity cache initialized")
        return adapter
    except Exception:
        logger.exception("Failed to initialize incident severity cache")
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


def get_ingest_event_service() -> IngestEventService:
    # Provide an ingest event service instance.
    try:
        service = IngestEventService(
            event_repository=EventRepositoryImpl(session_factory=get_db_session_factory()),
            realtime_counters=get_rolling_window(),
            incident_repository=IncidentRepositoryImpl(session_factory=get_db_session_factory()),
            incident_severity_cache=get_incident_severity_cache(),
            baseline_window_count=get_settings().baseline_window_count,
            incident_dedup_window_seconds=get_settings().incident_dedup_window_seconds,
            incident_escalation_window_medium_seconds=get_settings().incident_escalation_window_medium_seconds,
            incident_escalation_window_high_seconds=get_settings().incident_escalation_window_high_seconds,
            incident_escalation_min_hits_medium=get_settings().incident_escalation_min_hits_medium,
            incident_escalation_min_hits_high=get_settings().incident_escalation_min_hits_high,
            incident_escalation_score_threshold_medium=get_settings().incident_escalation_score_threshold_medium,
            incident_escalation_score_threshold_high=get_settings().incident_escalation_score_threshold_high,
            incident_escalation_ttl_seconds=get_settings().incident_escalation_ttl_seconds,
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
        )
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
            incident_severity_cache=get_incident_severity_cache(),
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


def get_protect_service() -> ProtectService:
    # Provide protect decision service.
    try:
        return ProtectService(
            ingest_key_service=get_ingest_key_service(),
            realtime_counters=get_rolling_window(),
            incident_severity_cache=get_incident_severity_cache(),
            protect_action_store=get_protect_action_store(),
            protect_block_cooldown_seconds=get_settings().protect_block_cooldown_seconds,
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    # Validate bearer token and load user.
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="not authenticated")
    token_payload = decode_access_token(
        token=credentials.credentials,
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


def _ensure_legacy_schema(session_factory: DatabaseSessionFactory) -> None:
    # Add backward-compatible columns for dev databases created before tenancy/auth.
    inspector = inspect(session_factory.engine)
    table_names = set(inspector.get_table_names())
    if "projects" not in table_names:
        return
    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "user_id" in project_columns:
        pass
    else:
        with session_factory.engine.begin() as connection:
            connection.execute(text("ALTER TABLE projects ADD COLUMN user_id VARCHAR(64)"))
    with session_factory.engine.begin() as connection:
        if "protect_enabled" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN protect_enabled BOOLEAN DEFAULT FALSE NOT NULL"))
        if "protect_fail_mode" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN protect_fail_mode VARCHAR(16) DEFAULT 'open' NOT NULL"))
        if "protect_max_req_per_min" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN protect_max_req_per_min INTEGER"))
        if "protect_max_tok_per_min" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN protect_max_tok_per_min INTEGER"))
        if "protect_decision_timeout_ms" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN protect_decision_timeout_ms INTEGER DEFAULT 100 NOT NULL"))
        if "webhook_enabled" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_enabled BOOLEAN DEFAULT FALSE NOT NULL"))
        if "webhook_url" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_url VARCHAR(2048)"))
        if "webhook_secret" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_secret VARCHAR(512)"))
        if "webhook_last_status" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_last_status VARCHAR(16)"))
        if "webhook_last_at" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_last_at TIMESTAMP"))
        if "webhook_last_error" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN webhook_last_error VARCHAR(512)"))

    if "incidents" not in table_names:
        return
    incident_columns = {column["name"] for column in inspector.get_columns("incidents")}
    with session_factory.engine.begin() as connection:
        if "fingerprint" not in incident_columns:
            connection.execute(text("ALTER TABLE incidents ADD COLUMN fingerprint VARCHAR(255)"))
        if "last_seen_at" not in incident_columns:
            connection.execute(text("ALTER TABLE incidents ADD COLUMN last_seen_at TIMESTAMP"))

    incident_indexes = {index["name"] for index in inspector.get_indexes("incidents")}
    if "ix_incidents_project_status_fingerprint" not in incident_indexes:
        with session_factory.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_incidents_project_status_fingerprint "
                    "ON incidents (project_id, status, fingerprint)"
                )
            )
    try:
        with session_factory.engine.begin() as connection:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_events_project_id_ts ON events (project_id, ts)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_events_ts ON events (ts)"))
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_incidents_project_status_created_at "
                    "ON incidents (project_id, status, created_at)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_ingest_keys_project_status "
                    "ON ingest_keys (project_id, status)"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_user_id_name "
                    "ON projects (user_id, name)"
                )
            )
    except Exception:
        logger.warning("Skipping one or more legacy index backfills; dev DB may require reset")
