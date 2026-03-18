# Application configuration objects.
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AppConfig:
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    default_protect_decision_timeout_ms: int = 150
    protect_outcome_source_live: str = "live"
    protect_outcome_source_timeout_fallback: str = "timeout_fallback"
    protect_outcome_source_unavailable_fallback: str = "unavailable_fallback"
    rolling_window_seconds: int = 60
    rolling_window_ms: int = rolling_window_seconds * 1000
    rolling_counter_ttl_seconds: int = 600
    rate_limit_window_seconds: int = 60
    incident_type_policy_gap: str = "policy_gap"
    incident_type_near_cap: str = "near_cap"
    incident_type_cap_breach: str = "cap_breach"
    incident_type_retry_storm: str = "retry_storm"
    incident_type_loop_suspect: str = "loop_suspect"
    incident_type_token_explosion: str = "token_explosion"
    retry_storm_window_seconds: int = 60
    retry_storm_count: int = 5
    loop_window_seconds: int = 30
    loop_count: int = 6
    token_explosion_ratio: float = 0.8
    token_explosion_abs: int = 6000
    protect_near_cap_factor: float = 0.85
    protect_action_counter_ttl_seconds: int = 3600
    webhook_retry_max_attempts: int = 3
    webhook_retry_intervals_seconds: tuple[int, int, int] = (5, 20, 60)
    webhook_timeout_connect_seconds: float = 2.0
    webhook_timeout_read_seconds: float = 5.0
    webhook_timeout_write_seconds: float = 5.0
    webhook_timeout_pool_seconds: float = 5.0
    webhook_max_error_chars: int = 240
    email_retry_max_attempts: int = 1
    email_retry_intervals_seconds: tuple[int, ...] = ()
    scheduler_default_result_ttl_seconds: int = 3600
    scheduler_default_failure_ttl_seconds: int = 86400
    purge_interval_seconds: int = 24 * 60 * 60
    db_slow_query_threshold_ms: float = 250.0
    name_max_length: int = 80
    email_max_length: int = 320
    name_validation_pattern: str = r"^[A-Za-z0-9 _.-]+$"
    email_validation_pattern: str = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    control_chars: tuple[str, str, str] = ("\r", "\n", "\t")


app_config = AppConfig()


class Settings(BaseSettings):
    # Runtime settings container for the backend service.
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "Rheonic API"
    api_prefix: str = "/api"
    app_env: str = "dev"
    log_level: str = "INFO"

    # Database settings.
    postgres_db: str = "rheonic"
    postgres_user: str = "rheonic"
    postgres_password: str = "change-me"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    jwt_expires_min: int = 60
    jwt_refresh_expires_min: int = 10080

    # Redis settings.
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # Provider/demo settings.
    rheonic_provider_url: str = "http://localhost:8099"
    rheonic_provider: str = "openai"
    rheonic_model: str = "gpt-4o-mini"
    rheonic_environment: str = "dev"
    rheonic_scenario: str = "allow"
    rheonic_demo_case: str = "steady"
    rheonic_base_url: str = "http://localhost:8000"
    rheonic_backend_url: str = "http://localhost:8000"
    rheonic_ingest_key: str = ""
    rheonic_project_id: str = ""

    cors_origins: str = ""
    database_url: str = ""
    redis_url: str = ""
    idempotency_ttl_seconds: int = 120
    ingest_rate_limit_per_minute: int = 600
    rate_limit_window_seconds: int = app_config.rate_limit_window_seconds
    auth_rate_limit_window_seconds: int = app_config.rate_limit_window_seconds
    auth_register_rate_limit_per_window: int = 10
    auth_login_rate_limit_per_window: int = 10
    auth_refresh_rate_limit_per_window: int = 30
    incident_dedup_window_seconds: int = 300
    retry_storm_window_seconds: int = app_config.retry_storm_window_seconds
    retry_storm_count: int = app_config.retry_storm_count
    loop_window_seconds: int = app_config.loop_window_seconds
    loop_count: int = app_config.loop_count
    token_explosion_ratio: float = app_config.token_explosion_ratio
    token_explosion_abs: int = app_config.token_explosion_abs
    incident_auto_close_seconds: int = 3600
    auto_close_run_interval_seconds: int = 60
    event_retention_days: int = 30
    protect_block_cooldown_seconds: int = 60
    protect_decision_timeout_ms: int = app_config.default_protect_decision_timeout_ms
    webhook_allow_private_hosts: bool = False
    email_provider_enabled: bool = False
    email_provider: str = ""
    resend_api_key: str = ""
    email_from_alerts: str = ""
    email_from_system: str = ""
    email_reply_to: str = ""
    public_contact_email: str = "contact@rheonic.dev"
    feedback_report_email: str = "feedback@rheonic.dev"
    rq_queue_name: str = "rheonic"
    rq_scheduler_interval_seconds: int = 15
    trust_proxy_headers: bool = False
    forwarded_allow_ips: str = "127.0.0.1"

    @property
    def app_env_normalized(self) -> str:
        return (self.app_env or "dev").strip().lower()

    @property
    def is_production_like(self) -> bool:
        return self.app_env_normalized in {"prod", "production", "staging"}

    @property
    def auth_cookie_secure(self) -> bool:
        return self.is_production_like

    @property
    def auth_cookie_samesite(self) -> str:
        return "lax"

    @property
    def auth_access_cookie_name(self) -> str:
        return "__Host-rheonic_access" if self.auth_cookie_secure else "rheonic_access"

    @property
    def auth_refresh_cookie_name(self) -> str:
        return "__Secure-rheonic_refresh" if self.auth_cookie_secure else "rheonic_refresh"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in (self.cors_origins or "").split(",") if origin.strip()]

    @property
    def resolved_email_provider(self) -> str:
        provider = (self.email_provider or "").strip().lower()
        if provider:
            return provider
        if (self.resend_api_key or "").strip():
            return "resend"
        return ""

    @property
    def resolved_email_provider_enabled(self) -> bool:
        if self.email_provider_enabled:
            return True
        provider = self.resolved_email_provider
        return provider == "resend" and bool((self.resend_api_key or "").strip())

    @model_validator(mode="after")
    def _apply_url_defaults(self) -> "Settings":
        # Build connection URLs from component env vars when explicit URLs are not provided.
        if not (self.database_url or "").strip():
            self.database_url = (
                f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        if not (self.redis_url or "").strip():
            redis_auth = f":{self.redis_password}@" if self.redis_password else ""
            self.redis_url = f"redis://{redis_auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        elif self.redis_password:
            parsed = urlsplit(self.redis_url)
            if parsed.scheme.startswith("redis") and parsed.hostname and parsed.password is None:
                redis_netloc = parsed.hostname
                if parsed.port is not None:
                    redis_netloc = f"{redis_netloc}:{parsed.port}"
                parsed = SplitResult(
                    scheme=parsed.scheme,
                    netloc=f":{self.redis_password}@{redis_netloc}",
                    path=parsed.path,
                    query=parsed.query,
                    fragment=parsed.fragment,
                )
                self.redis_url = urlunsplit(parsed)
        return self

    @model_validator(mode="after")
    def _validate_deploy_safety(self) -> "Settings":
        # Enforce stricter requirements in staging/production-like environments.
        allowed_envs = {"dev", "test", "staging", "prod", "production"}
        if self.app_env_normalized not in allowed_envs:
            raise ValueError(f"APP_ENV must be one of {sorted(allowed_envs)}")
        if self.is_production_like:
            jwt = (self.jwt_secret or "").strip()
            if len(jwt) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in staging/production")
            if not self.cors_origin_list:
                raise ValueError("CORS_ORIGINS is required in staging/production")
            lowered = ",".join(self.cors_origin_list).lower()
            if "localhost" in lowered or "127.0.0.1" in lowered:
                raise ValueError("CORS_ORIGINS must not contain localhost in staging/production")
        return self

    @model_validator(mode="after")
    def _validate_email_configuration(self) -> "Settings":
        provider = self.resolved_email_provider
        if provider and provider not in {"resend"}:
            raise ValueError("EMAIL_PROVIDER must be 'resend' when configured")
        if not self.resolved_email_provider_enabled:
            return self
        if provider != "resend":
            raise ValueError("RESEND_API_KEY is required when email delivery is enabled")
        if not (self.resend_api_key or "").strip():
            raise ValueError("RESEND_API_KEY is required when email delivery is enabled")
        if not (self.email_from_alerts or "").strip():
            raise ValueError("EMAIL_FROM_ALERTS is required when email delivery is enabled")
        if not (self.email_from_system or "").strip():
            raise ValueError("EMAIL_FROM_SYSTEM is required when email delivery is enabled")
        if not (self.email_reply_to or "").strip():
            raise ValueError("EMAIL_REPLY_TO is required when email delivery is enabled")
        return self
