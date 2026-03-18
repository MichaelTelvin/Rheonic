from __future__ import annotations

import json
import logging

from app.logger import _JsonLogFormatter, bind_trace_context, build_log_extra, reset_trace_context


def test_json_log_formatter_emits_contract_shape_and_redacts_sensitive_fields() -> None:
    formatter = _JsonLogFormatter()
    logger = logging.getLogger("app.tests.logger")
    tokens = bind_trace_context(trace_id="trace-123", span_id="span-456")
    try:
        record = logger.makeRecord(
            name=logger.name,
            level=logging.INFO,
            fn=__file__,
            lno=10,
            msg="Webhook sent",
            args=(),
            exc_info=None,
            extra=build_log_extra(
                event="webhook_sent",
                metadata={
                    "destination": "https://example.test/hook",
                    "api_key": "should-not-appear",
                },
            ),
        )
        payload = json.loads(formatter.format(record))
    finally:
        reset_trace_context(tokens)

    assert payload["level"] == "info"
    assert payload["trace_id"] == "trace-123"
    assert payload["span_id"] == "span-456"
    assert payload["event"] == "webhook_sent"
    assert payload["message"] == "Webhook sent"
    assert payload["metadata"]["destination"] == "https://example.test/hook"
    assert payload["metadata"]["api_key"] == "[REDACTED]"
