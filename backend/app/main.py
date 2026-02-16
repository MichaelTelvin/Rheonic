# FastAPI application entrypoint.
from fastapi import FastAPI

from app.api.routers import api_router
from app.config import Settings
from app.logger import configure_logging, get_logger

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    # Create and configure the FastAPI application instance.
    configure_logging()
    _settings = settings or Settings()
    app = FastAPI(title=_settings.app_name)

    # all the routes go here
    @app.get("/health")
    def health() -> dict[str, str]:
        # Return a basic health response.
        try:
            logger.debug("Health endpoint called")
            return {"status": "ok"}
        except Exception:
            logger.exception("Health endpoint failed")
            raise

    # register routers
    app.include_router(api_router, prefix=_settings.api_prefix)
    logger.info("FastAPI app initialized", extra={"api_prefix": _settings.api_prefix})
    return app


app = create_app()
