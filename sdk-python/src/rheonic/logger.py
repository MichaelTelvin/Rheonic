from __future__ import annotations

import json
import logging
import os
import re
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from rheonic.config import sdk_config

_TRACE_ID: ContextVar[str] = ContextVar("sdk_trace_id", default="")
_SPAN_ID: ContextVar[str] = ContextVar("sdk_span_id", default="")
_SERVICE_NAME = "sdk-python"
_ENV_NAME = sdk_config.default_environment
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
_SENSITIVE_FIELD_MARKERS = ("api_key", "apikey", "authorization", "cookie", "password", "secret", "token")
_EVENT_SANITIZER = re.compile(r"[^a-z0-9_]+")


def configure_logging(
    *, service_name: str = "sdk-python", level: str | None = None, environment: str | None = None
) -> None:
    global _SERVICE_NAME, _ENV_NAME
    configured_level = level if level is not None else os.getenv("RHEONIC_LOG_LEVEL")
    resolved_level = (configured_level or "INFO").upper()
    _SERVICE_NAME = service_name
    _ENV_NAME = (
        (
            environment
            or os.getenv("NODE_ENV")
            or os.getenv("APP_ENV")
            or os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or sdk_config.default_environment
        )
        .strip()
        .lower()
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)
    # Keep third-party transport chatter out of normal SDK output.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


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


def build_log_extra(
    *, event: str, metadata: dict[str, Any] | None = None, trace_id: str | None = None, span_id: str | None = None
) -> dict[str, Any]:
    return {
        "event": event,
        "metadata": metadata or {},
        "trace_id": trace_id,
        "span_id": span_id,
    }


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        metadata = _build_metadata(record)
        if record.exc_info:
            metadata.setdefault("error_message", str(record.exc_info[1]))
            metadata.setdefault("stack_trace", self.formatException(record.exc_info))
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": _normalize_level(record.levelname),
            "service": _SERVICE_NAME,
            "env": _ENV_NAME,
            "trace_id": _resolve_string(getattr(record, "trace_id", None)) or get_trace_id(),
            "span_id": _resolve_string(getattr(record, "span_id", None)) or get_span_id(),
            "event": _resolve_event(record, message),
            "message": message,
            "metadata": metadata,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _build_metadata(record: logging.LogRecord) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    record_metadata = getattr(record, "metadata", None)
    if isinstance(record_metadata, dict):
        metadata.update(_sanitize_value(record_metadata))
    for key, value in record.__dict__.items():
        if key in _RESERVED_EXTRA_FIELDS or key in {"event", "metadata", "trace_id", "span_id"}:
            continue
        metadata[key] = _sanitize_value(value, key=key)
    return metadata


def _sanitize_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and any(marker in key.lower() for marker in _SENSITIVE_FIELD_MARKERS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _resolve_event(record: logging.LogRecord, message: str) -> str:
    explicit_event = _resolve_string(getattr(record, "event", None))
    if explicit_event:
        return _sanitize_event(explicit_event)
    if record.exc_info:
        return "error"
    return _sanitize_event(message)


def _sanitize_event(value: str) -> str:
    normalized = _EVENT_SANITIZER.sub("_", value.strip().lower()).strip("_")
    return normalized or "log"


def _normalize_level(level_name: str) -> str:
    normalized = (level_name or "info").strip().lower()
    return "warn" if normalized == "warning" else normalized


def _resolve_string(value: Any) -> str:
    return "" if value is None else str(value).strip()
