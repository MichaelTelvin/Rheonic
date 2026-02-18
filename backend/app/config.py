# Application configuration objects.
from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AppConfig:
    default_log_format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    rolling_window_seconds: int = 60
    rolling_window_ms: int = rolling_window_seconds * 1000
    rolling_counter_ttl_seconds: int = 600
    baseline_counter_ttl_seconds: int = 3600


app_config = AppConfig()


class Settings(BaseSettings):
    # Runtime settings container for the backend service.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LLMTokenBurnGuard API"
    api_prefix: str = "/api"
    app_env: str = "dev"
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    jwt_expires_min: int = 60
    cors_origins: str = ""
    database_url: str = ""
    redis_url: str = ""
    baseline_window_count: int = 30
    incident_dedup_window_seconds: int = 300

    # TODO: Add env-driven database, Redis, auth, and provider settings.
