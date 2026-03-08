# FastAPI application entrypoint.
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text

from app.api.error_responses import build_error_response, default_code_for_status
from app.api.routers import api_router
from app.config import Settings
from app.dependencies import get_db_session_factory, get_redis_client
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
                user_id=None,
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
        yield
    except Exception:
        logger.exception("Application startup failed")
        raise


def create_app(settings: Settings | None = None) -> FastAPI:
    # Create and configure the FastAPI application instance.
    configure_logging()
    _settings = settings or Settings()
    app = FastAPI(title=_settings.app_name, lifespan=lifespan)
    origins = _settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or (["http://localhost:5173"] if _settings.app_env_normalized == "dev" else []),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Project-Ingest-Key", "X-Idempotency-Key"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        logger.info(
            "HTTP request started",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request_id)
        logger.info(
            "HTTP request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        # Apply baseline browser hardening headers for API and frontend clients.
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Return standardized error payloads for known API failures.
        logger.warning(
            "HTTP exception raised",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
            },
        )
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = exc.detail["error"]
            code = str(payload.get("code") or default_code_for_status(exc.status_code))
            message = str(payload.get("message") or "request failed")
            return build_error_response(exc.status_code, code, message)
        message = str(exc.detail) if exc.detail else "request failed"
        return build_error_response(exc.status_code, default_code_for_status(exc.status_code), message)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Hide unexpected exception internals from clients.
        logger.exception(
            "Unhandled application exception",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
            },
        )
        _ = exc
        return build_error_response(500, "internal_error", "Internal server error")

    # all the routes go here
    @app.get("/health")
    def health() -> dict[str, str]:
        # Liveness endpoint for process-level checks.
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        # Readiness endpoint verifies DB and Redis dependencies.
        try:
            with get_db_session_factory().create_session() as session:
                session.execute(text("SELECT 1"))
            if not get_redis_client().ping():
                raise RuntimeError("redis ping failed")
            return {"status": "ready"}
        except Exception as exc:
            logger.exception("Readiness check failed")
            raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc

    # register routers
    app.include_router(api_router, prefix=_settings.api_prefix)
    logger.info(
        "FastAPI app initialized",
        extra={"api_prefix": _settings.api_prefix, "app_env": _settings.app_env_normalized},
    )
    return app


app = create_app()
