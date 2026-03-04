# Application configuration objects.
from dataclasses import dataclass

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AppConfig:
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
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
    webhook_result_ttl_seconds: int = 3600
    webhook_failure_ttl_seconds: int = 86400
    webhook_timeout_connect_seconds: float = 2.0
    webhook_timeout_read_seconds: float = 5.0
    webhook_timeout_write_seconds: float = 5.0
    webhook_timeout_pool_seconds: float = 5.0
    webhook_max_error_chars: int = 240
    webhook_secret_prefix: str = "enc:v1:"
    webhook_secret_default_fallback_key: str = "rheonic-webhook-secret-default"
    scheduler_default_result_ttl_seconds: int = 3600
    scheduler_default_failure_ttl_seconds: int = 86400
    purge_interval_seconds: int = 24 * 60 * 60
    name_max_length: int = 80
    email_max_length: int = 320
    name_validation_pattern: str = r"^[A-Za-z0-9 _.-]+$"
    email_validation_pattern: str = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    control_chars: tuple[str, str, str] = ("\r", "\n", "\t")


app_config = AppConfig()


class Settings(BaseSettings):
    # Runtime settings container for the backend service.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    rheonic_auth_token: str = ""

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
    incident_dedup_window_seconds: int = 300
    retry_storm_window_seconds: int = app_config.retry_storm_window_seconds
    retry_storm_count: int = app_config.retry_storm_count
    loop_window_seconds: int = app_config.loop_window_seconds
    loop_count: int = app_config.loop_count
    token_explosion_ratio: float = app_config.token_explosion_ratio
    token_explosion_abs: int = app_config.token_explosion_abs
    incident_auto_close_seconds: int = 300
    auto_close_run_interval_seconds: int = 60
    event_retention_days: int = 30
    protect_block_cooldown_seconds: int = 60
    webhook_allow_private_hosts: bool = False
    webhook_secret_encryption_key: str = ""
    public_contact_email: str = "owldevlab@gmail.com"
    feedback_report_email: str = "owldevlab@gmail.com"
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_use_ssl: bool = False

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
        return self
