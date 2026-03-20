from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import Settings

_TRACE_ID: ContextVar[str] = ContextVar("trace_id", default="")
_SPAN_ID: ContextVar[str] = ContextVar("span_id", default="")
_SENSITIVE_FIELD_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)
_RESERVED_EXTRA_FIELDS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}
_EVENT_SANITIZER = re.compile(r"[^a-z0-9_]+")
_SERVICE_NAME = "backend"
_ENV_NAME = "dev"


def generate_trace_id() -> str:
    return str(uuid4())


def generate_span_id() -> str:
    return uuid4().hex[:16]


def bind_trace_context(*, trace_id: str | None = None, span_id: str | None = None) -> tuple[Token[str], Token[str]]:
    resolved_trace_id = (trace_id or "").strip() or generate_trace_id()
    resolved_span_id = (span_id or "").strip() or generate_span_id()
    return (_TRACE_ID.set(resolved_trace_id), _SPAN_ID.set(resolved_span_id))


def reset_trace_context(tokens: tuple[Token[str], Token[str]]) -> None:
    trace_token, span_token = tokens
    _TRACE_ID.reset(trace_token)
    _SPAN_ID.reset(span_token)


def get_trace_id() -> str:
    return _TRACE_ID.get().strip()


def get_span_id() -> str:
    return _SPAN_ID.get().strip()


class _JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        metadata = _build_metadata(record)
        if record.exc_info:
            metadata.setdefault("error_message", str(record.exc_info[1]))
            metadata.setdefault("stack_trace", self.formatException(record.exc_info))
        elif record.stack_info:
            metadata.setdefault("stack_trace", str(record.stack_info))
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": _normalize_level(record.levelname),
            "service": getattr(record, "service", None) or _SERVICE_NAME,
            "env": getattr(record, "env", None) or _ENV_NAME,
            "trace_id": _resolve_string(getattr(record, "trace_id", None)) or get_trace_id(),
            "span_id": _resolve_string(getattr(record, "span_id", None)) or get_span_id(),
            "event": _resolve_event(record, message),
            "message": message,
            "metadata": metadata,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(*, service_name: str = "backend", level: str | None = None) -> None:
    global _SERVICE_NAME, _ENV_NAME

    settings = Settings()
    _SERVICE_NAME = service_name.strip() or "backend"
    _ENV_NAME = settings.app_env_normalized
    resolved_level = (level or settings.log_level).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)

    for logger_name in ("uvicorn", "fastapi"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(resolved_level)
        logger.propagate = True

    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.handlers.clear()
    uvicorn_error_logger.setLevel(logging.WARNING)
    uvicorn_error_logger.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.setLevel(logging.WARNING)
    access_logger.propagate = False

    for logger_name in ("rq", "rq.worker", "rq.job", "rq.queue", "rq_scheduler", "httpx", "httpcore"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def build_log_extra(*, event: str, metadata: dict[str, Any] | None = None, trace_id: str | None = None, span_id: str | None = None) -> dict[str, Any]:
    return {
        "event": event,
        "metadata": metadata or {},
        "trace_id": trace_id,
        "span_id": span_id,
    }


def _normalize_level(level_name: str) -> str:
    normalized = (level_name or "info").strip().lower()
    if normalized == "warning":
        return "warn"
    if normalized not in {"debug", "info", "warn", "error"}:
        return "info"
    return normalized


def _resolve_event(record: logging.LogRecord, message: str) -> str:
    explicit_event = _resolve_string(getattr(record, "event", None))
    if explicit_event:
        return _sanitize_event_name(explicit_event)
    if record.exc_info:
        return "error"
    if not message:
        return "log"
    return _sanitize_event_name(message)


def _sanitize_event_name(value: str) -> str:
    normalized = _EVENT_SANITIZER.sub("_", value.strip().lower()).strip("_")
    return normalized or "log"


def _build_metadata(record: logging.LogRecord) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    record_metadata = getattr(record, "metadata", None)
    if isinstance(record_metadata, dict):
        metadata.update(_sanitize_value(record_metadata))
    for key, value in record.__dict__.items():
        if key in _RESERVED_EXTRA_FIELDS or key in {"event", "metadata", "trace_id", "span_id", "service", "env"}:
            continue
        metadata[key] = _sanitize_value(value, key=key)
    return metadata


def _sanitize_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize_value(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(marker in lowered for marker in _SENSITIVE_FIELD_MARKERS)


def _resolve_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
