# FastAPI application entrypoint.
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.api.routers import api_router
from app.config import Settings
from app.dependencies import get_db_session_factory
from app.domain.models.project import Project
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.logger import configure_logging, get_logger

logger = get_logger(__name__)


def _seed_demo_project() -> None:
    # Seed a local demo project when the projects table is empty.
    try:
        repository = ProjectRepositoryImpl(session_factory=get_db_session_factory())
        projects = repository.list_projects()
        if projects:
            logger.debug("Project seed skipped because projects already exist", extra={"count": len(projects)})
            return

        repository.create_project(
            Project(
                id="p1",
                name="Demo Project",
                created_at=datetime.now(timezone.utc),
            )
        )
        logger.info("Demo project seeded", extra={"project_id": "p1"})
    except Exception:
        logger.exception("Failed seeding demo project")
        raise


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize startup resources and seed local data.
    try:
        get_db_session_factory()
        _seed_demo_project()
        yield
    except Exception:
        logger.exception("Application startup failed")
        raise


def create_app(settings: Settings | None = None) -> FastAPI:
    # Create and configure the FastAPI application instance.
    configure_logging()
    _settings = settings or Settings()
    app = FastAPI(title=_settings.app_name, lifespan=lifespan)

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
