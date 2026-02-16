# Application configuration objects.
from pydantic import BaseModel


class Settings(BaseModel):
    # Runtime settings container for the backend service.
    app_name: str = "LLMTokenBurnGuard API"
    api_prefix: str = "/api"
    threshold_tokens_60s: int = 50_000
    threshold_req_60s: int = 200
    incident_lock_ttl_seconds: int = 1800

    # TODO: Add env-driven database, Redis, auth, and provider settings.
