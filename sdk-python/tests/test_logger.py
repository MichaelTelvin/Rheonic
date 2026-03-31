from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from rheonic import logger as logger_module


def test_configure_logging_sets_root_and_third_party_levels(monkeypatch: Any) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    logger_module.configure_logging(service_name="sdk-test", level="debug", environment="Staging")
    assert logger_module._SERVICE_NAME == "sdk-test"
    assert logger_module._ENV_NAME == "staging"
    assert root.level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    monkeypatch.setenv("RHEONIC_LOG_LEVEL", "warning")
    logger_module.configure_logging()
    assert logging.getLogger().level == logging.WARNING


def test_trace_context_helpers_round_trip() -> None:
    tokens = logger_module.bind_trace_context(trace_id=" trace ", span_id=" span ")
    assert logger_module.get_trace_id() == "trace"
    assert logger_module.get_span_id() == "span"
    logger_module.reset_trace_context(tokens)


def test_build_log_extra_and_resolve_helpers() -> None:
    extra = logger_module.build_log_extra(event="sdk_event", metadata={"ok": True}, trace_id="t", span_id="s")
    assert extra == {"event": "sdk_event", "metadata": {"ok": True}, "trace_id": "t", "span_id": "s"}
    assert logger_module._resolve_string(None) == ""
    assert logger_module._resolve_string(" x ") == "x"
    assert logger_module._normalize_level("WARNING") == "warn"
    assert logger_module._normalize_level("INFO") == "info"
    assert logger_module._sanitize_event("HTTP Request: POST /x") == "http_request_post_x"
    assert logger_module._sanitize_event("!!!") == "log"


def test_sanitize_value_redacts_sensitive_and_serializes_nested_values() -> None:
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    value = logger_module._sanitize_value(
        {
            "api_key": "secret",
            "nested": {"token": "hidden", "when": dt},
            "items": [SimpleNamespace(name="x"), 1, True, None],
        }
    )
    assert value["api_key"] == "[REDACTED]"
    assert value["nested"]["token"] == "[REDACTED]"
    assert value["nested"]["when"] == dt.isoformat()
    assert value["items"][0].startswith("namespace(")


def test_build_metadata_filters_reserved_fields_and_sanitizes_values() -> None:
    record = logging.LogRecord("sdk", logging.INFO, __file__, 10, "hello", (), None)
    record.metadata = {"password": "secret", "safe": 1}
    record.trace_id = "trace"
    record.span_id = "span"
    record.custom = {"cookie": "abc", "ok": "yes"}
    metadata = logger_module._build_metadata(record)
    assert metadata["password"] == "[REDACTED]"
    assert metadata["safe"] == 1
    assert metadata["custom"]["cookie"] == "[REDACTED]"
    assert "trace_id" not in metadata
    assert "span_id" not in metadata


def test_resolve_event_prefers_explicit_then_error_then_message() -> None:
    record = logging.LogRecord("sdk", logging.INFO, __file__, 10, "Hello There", (), None)
    record.event = "custom event"
    assert logger_module._resolve_event(record, "ignored") == "custom_event"
    record.event = None
    record.exc_info = (RuntimeError, RuntimeError("boom"), None)
    assert logger_module._resolve_event(record, "ignored") == "error"
    record.exc_info = None
    assert logger_module._resolve_event(record, "Hello There") == "hello_there"


def test_json_formatter_includes_exception_and_context_fields() -> None:
    formatter = logger_module._JsonFormatter()
    tokens = logger_module.bind_trace_context(trace_id="trace-1", span_id="span-1")
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = logging.LogRecord("sdk", logging.ERROR, __file__, 10, "Failed", (), None)
            record.metadata = {"authorization": "token", "count": 3}
            record.exc_info = sys.exc_info()
            payload = json.loads(formatter.format(record))
    finally:
        logger_module.reset_trace_context(tokens)

    assert payload["level"] == "error"
    assert payload["service"] == logger_module._SERVICE_NAME
    assert payload["trace_id"] == "trace-1"
    assert payload["span_id"] == "span-1"
    assert payload["event"] == "error"
    assert payload["metadata"]["authorization"] == "[REDACTED]"
    assert payload["metadata"]["error_message"] == "boom"
    assert "RuntimeError: boom" in payload["metadata"]["stack_trace"]


def test_json_formatter_generates_trace_and_span_when_unbound() -> None:
    formatter = logger_module._JsonFormatter()
    record = logging.LogRecord("sdk", logging.INFO, __file__, 10, "hello", (), None)
    payload = json.loads(formatter.format(record))

    assert isinstance(payload["trace_id"], str)
    assert payload["trace_id"] != ""
    assert isinstance(payload["span_id"], str)
    assert payload["span_id"] != ""
