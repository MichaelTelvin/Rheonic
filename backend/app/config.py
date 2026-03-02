# Application configuration objects.
from dataclasses import dataclass

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
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    jwt_expires_min: int = 60
    jwt_refresh_expires_min: int = 10080
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

    # TODO: Add env-driven database, Redis, auth, and provider settings.
