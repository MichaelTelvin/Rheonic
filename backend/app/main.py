"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routers import api_router
from app.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    _settings = settings or Settings()
    app = FastAPI(title=_settings.app_name)

    # all the routes go here

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}
    
    app.include_router(api_router, prefix=_settings.api_prefix)
    return app


app = create_app()
