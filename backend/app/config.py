# Application configuration objects.
from pydantic import BaseModel


class Settings(BaseModel):
    # Runtime settings container for the backend service.
    app_name: str = "LLMTokenBurnGuard API"
    api_prefix: str = "/api"

    # TODO: Add env-driven database, Redis, auth, and provider settings.
