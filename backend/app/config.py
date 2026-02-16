# Application configuration objects.
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Runtime settings container for the backend service.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LLMTokenBurnGuard API"
    api_prefix: str = "/api"
    app_env: str = "dev"
    jwt_secret: str = ""
    cors_origins: str = ""
    database_url: str = ""
    redis_url: str = ""
    threshold_tokens_60s: int = 50_000
    threshold_req_60s: int = 200
    incident_lock_ttl_seconds: int = 1800

    # TODO: Add env-driven database, Redis, auth, and provider settings.
