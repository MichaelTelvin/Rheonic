# FastAPI application entrypoint.
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.error_responses import build_error_response, default_code_for_status
from app.api.routers import api_router
from app.config import Settings
from app.dependencies import get_db_session_factory
from app.health_checks import assert_critical_dependencies_ready
from app.logger import (
    bind_trace_context,
    build_log_extra,
    configure_logging,
    generate_span_id,
    generate_trace_id,
    get_logger,
    reset_trace_context,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Initialize startup resources and seed local data.
    try:
        get_db_session_factory()
        yield
    except Exception:
        logger.exception("Application startup failed")
        raise


def create_app(settings: Settings | None = None) -> FastAPI:
    # Create and configure the FastAPI application instance.
    _settings = settings or Settings()
    configure_logging(service_name="backend", level=_settings.log_level)
    app = FastAPI(title=_settings.app_name, lifespan=lifespan)
    origins = _settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or (["http://localhost:5173"] if _settings.app_env_normalized == "dev" else []),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Accept",
            "Origin",
            "X-Project-Ingest-Key",
            "X-Idempotency-Key",
            "X-Trace-ID",
            "X-Span-ID",
            "X-Request-ID",
            "X-Rheonic-Protect-Request-Id",
        ],
    )

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID") or generate_trace_id()
        span_id = request.headers.get("X-Span-ID") or generate_span_id()
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Rheonic-Protect-Request-Id")
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.request_id = request_id
        context_tokens = bind_trace_context(trace_id=trace_id, span_id=span_id)
        try:
            response = await call_next(request)
        except Exception:
            reset_trace_context(context_tokens)
            raise
        response.headers.setdefault("X-Trace-ID", trace_id)
        response.headers.setdefault("X-Span-ID", span_id)
        if request_id:
            response.headers.setdefault("X-Request-ID", request_id)
        response.headers.setdefault("X-App-Version", _settings.app_version)
        reset_trace_context(context_tokens)
        return response

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
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
    async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
        # Return standardized error payloads for known API failures.
        logger.warning(
            "HTTP exception raised",
            extra=build_log_extra(
                event="http_error",
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": exc.status_code,
                },
                trace_id=getattr(request.state, "trace_id", None),
                span_id=getattr(request.state, "span_id", None),
            ),
        )
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = exc.detail["error"]
            code = str(payload.get("code") or default_code_for_status(exc.status_code))
            message = str(payload.get("message") or "request failed")
            return build_error_response(exc.status_code, code, message)
        message = str(exc.detail) if exc.detail else "request failed"
        return build_error_response(exc.status_code, default_code_for_status(exc.status_code), message)

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
        # Keep legacy 422 semantics for general API validation, while treating
        # strict ingest/protect payload shape errors as bad requests.
        details = exc.errors()
        message = str(details[0].get("msg") if details else "invalid request payload")
        status_code = (
            400
            if request.url.path.startswith("/api/v1/events") or request.url.path.startswith("/api/v1/protect")
            else 422
        )
        logger.warning(
            "Request validation failed",
            extra=build_log_extra(
                event="http_error",
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "validation_error_count": len(details),
                },
                trace_id=getattr(request.state, "trace_id", None),
                span_id=getattr(request.state, "span_id", None),
            ),
        )
        return build_error_response(status_code, default_code_for_status(status_code), message)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        # Hide unexpected exception internals from clients.
        logger.exception(
            "Unhandled application exception",
            extra=build_log_extra(
                event="error",
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                },
                trace_id=getattr(request.state, "trace_id", None),
                span_id=getattr(request.state, "span_id", None),
            ),
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
            assert_critical_dependencies_ready()
            return {"status": "ready"}
        except Exception as exc:
            logger.exception("Readiness check failed")
            raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc

    # register routers
    app.include_router(api_router, prefix=_settings.api_prefix)
    logger.info(
        "FastAPI app initialized",
        extra={
            "api_prefix": _settings.api_prefix,
            "app_env": _settings.app_env_normalized,
            "app_version": _settings.app_version,
        },
    )
    return app


app = create_app()
