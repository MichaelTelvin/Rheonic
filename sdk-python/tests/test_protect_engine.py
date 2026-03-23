# Tests for protect preflight behavior in OpenAI instrumentation.
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import pytest
from rheonic import protect_engine as protect_engine_module
from rheonic.client import Client
from rheonic.protect_engine import ProtectEngine, RHEONICBlockedError, RHEONICValidationError, _parse_blocked_until_ms
from rheonic.provider_model_validation import validate_provider_model
from rheonic.providers.anthropic_adapter import (
    _set_token_estimator_for_tests as _set_anthropic_token_estimator_for_tests,
)
from rheonic.providers.anthropic_adapter import (
    instrument_anthropic,
)
from rheonic.providers.google_adapter import (
    _set_token_estimator_for_tests as _set_google_token_estimator_for_tests,
)
from rheonic.providers.google_adapter import (
    instrument_google,
)
from rheonic.providers.openai_adapter import _set_token_estimator_for_tests, instrument_openai


class FakeResponse:
    # Minimal response object for SDK transport tests.

    def __init__(
        self, status_code: int, payload: dict[str, Any] | None = None, json_error: Exception | None = None
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._json_error = json_error

    def json(self) -> dict[str, Any]:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class FakeHttpClient:
    # Fake HTTP transport that routes protect decisions and ingest calls.

    def __init__(self, decision: dict[str, Any] | Exception, decision_status: int = 200) -> None:
        self.decision = decision
        self.decision_status = decision_status
        self.calls: list[str] = []
        self.ingested_events: list[dict[str, Any]] = []
        self.decision_payloads: list[dict[str, Any]] = []
        self.timeout_reports: list[dict[str, Any]] = []
        self.unavailable_reports: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], **kwargs: Any) -> FakeResponse:
        _ = headers
        _ = kwargs
        self.calls.append(url)
        if url.endswith("/api/v1/protect/decision-timeout"):
            self.timeout_reports.append(json)
            return FakeResponse(status_code=202, payload={"status": "accepted"})
        if url.endswith("/api/v1/protect/decision-unavailable"):
            self.unavailable_reports.append(json)
            return FakeResponse(status_code=202, payload={"status": "accepted"})
        if url.endswith("/api/v1/protect/decision"):
            self.decision_payloads.append(json)
            if isinstance(self.decision, Exception):
                raise self.decision
            if self.decision_status != 200:
                return FakeResponse(status_code=self.decision_status, payload=self.decision)
            if self.decision.get("invalid_json"):
                return FakeResponse(status_code=200, json_error=ValueError("invalid json"))
            return FakeResponse(status_code=200, payload=self.decision)
        self.ingested_events.append(json)
        return FakeResponse(status_code=202, payload={"status": "accepted"})

    def close(self) -> None:
        return


def _wait_for_timeout_reports(transport: FakeHttpClient, expected: int) -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if len(transport.timeout_reports) >= expected:
            return
        time.sleep(0.01)


def _make_openai_stub() -> tuple[Any, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    class _Completions:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return type("Response", (), {"model": "gpt-4o-mini", "usage": type("Usage", (), {"total_tokens": 10})()})()

    class _Chat:
        completions = _Completions()

    class _OpenAI:
        chat = _Chat()

    return _OpenAI(), calls


def _make_anthropic_stub() -> tuple[Any, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            usage = type("Usage", (), {"input_tokens": 11, "output_tokens": 14})()
            return type("Response", (), {"model": "claude-3-5-sonnet", "usage": usage})()

    class _Anthropic:
        messages = _Messages()

    return _Anthropic(), calls


def _make_google_stub() -> tuple[Any, list[tuple[tuple[Any, ...], dict[str, Any]]]]:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _UsageMetadata:
        total_token_count = 27

    class _GoogleResponse:
        usage_metadata = _UsageMetadata()

    class _GoogleModel:
        model_name = "gemini-1.5-pro"

        def generate_content(self, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return _GoogleResponse()

    return _GoogleModel(), calls


def test_preflight_decision_endpoint_is_called_before_provider_request() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    decision_calls = [url for url in transport.calls if url.endswith("/api/v1/protect/decision")]
    assert len(decision_calls) == 1
    assert len(calls) == 1
    client.close()


def test_token_estimation_is_evaluated_before_protect_decision_request() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    estimator_calls = {"count": 0}

    def _counting_estimator(_payload: dict[str, Any]) -> int:
        estimator_calls["count"] += 1
        return 123

    _set_token_estimator_for_tests(_counting_estimator)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
    )
    decision_calls = [url for url in transport.calls if url.endswith("/api/v1/protect/decision")]
    assert len(decision_calls) == 1
    assert len(calls) == 1
    assert estimator_calls["count"] == 1
    _set_token_estimator_for_tests(None)
    client.close()


def test_preflight_block_prevents_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(  # type: ignore[arg-type]
            {
                "decision": "block",
                "reason": "tok_limit",
                "fail_mode": "open",
                "protect_decision_timeout_ms": 100,
            }
        ),
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    client.close()


def test_blocked_until_short_circuits_subsequent_decision_calls_locally() -> None:
    blocked_until = datetime.now(timezone.utc).timestamp() + 60
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "block",
            "reason": "req_limit",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
            "blocked_until": datetime.fromtimestamp(blocked_until, tz=timezone.utc).isoformat(),
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    decision_calls = [url for url in transport.calls if url.endswith("/api/v1/protect/decision")]
    assert len(decision_calls) == 1
    assert calls == []
    client.close()


def test_parallel_calls_during_active_cooldown_block_locally_without_backend_decision_calls() -> None:
    blocked_until = datetime.now(timezone.utc).timestamp() + 60
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "block",
            "reason": "req_limit",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
            "blocked_until": datetime.fromtimestamp(blocked_until, tz=timezone.utc).isoformat(),
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    # Prime cooldown from backend once.
    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    decision_calls_before = len([url for url in transport.calls if url.endswith("/api/v1/protect/decision")])
    assert decision_calls_before == 1

    def _invoke() -> None:
        with pytest.raises(RHEONICBlockedError):
            openai_client.chat.completions.create(model="gpt-4o-mini")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_invoke), pool.submit(_invoke)]
        for future in futures:
            future.result()

    decision_calls_after = len([url for url in transport.calls if url.endswith("/api/v1/protect/decision")])
    assert decision_calls_after == 1
    assert calls == []
    client.close()


def test_preflight_predictive_near_cap_warn_allows_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(  # type: ignore[arg-type]
            {
                "decision": "warn",
                "reason": "near_cap",
                "fail_mode": "open",
                "protect_decision_timeout_ms": 100,
            }
        ),
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini", max_tokens=1024)
    assert len(calls) == 1
    client.close()


def test_preflight_warn_allows_provider_call_and_tags_telemetry() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "warn",
            "reason": "loop_suspect",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    client.flush()
    assert len(calls) == 1
    assert len(transport.ingested_events) == 1
    request_payload = transport.ingested_events[0].get("request") or {}
    assert request_payload.get("protect_decision") == "warn"
    assert request_payload.get("protect_reason") == "loop_suspect"
    client.close()


def test_messages_request_includes_input_tokens_estimate() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    _set_token_estimator_for_tests(lambda _payload: 222)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, _ = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hello"}])
    assert len(transport.decision_payloads) == 1
    assert transport.decision_payloads[0]["input_tokens_estimate"] == 222
    _set_token_estimator_for_tests(None)
    client.close()


def test_token_estimation_failure_omits_input_tokens_estimate() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    _set_token_estimator_for_tests(lambda _payload: None)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, _ = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hello"}])
    assert len(transport.decision_payloads) == 1
    assert "input_tokens_estimate" not in transport.decision_payloads[0]
    _set_token_estimator_for_tests(None)
    client.close()


def test_preflight_timeout_fail_open_allows_provider_call() -> None:
    transport = FakeHttpClient(TimeoutError("timeout"))  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        environment="dev",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    _wait_for_timeout_reports(transport, expected=1)
    assert len(transport.timeout_reports) == 1
    assert transport.timeout_reports[0]["environment"] == "dev"
    assert transport.timeout_reports[0]["provider"] == "openai"
    client.close()


def test_preflight_timeout_fail_closed_blocks_provider_call() -> None:
    transport = FakeHttpClient(TimeoutError("timeout"))  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        environment="staging",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    _wait_for_timeout_reports(transport, expected=1)
    assert len(transport.timeout_reports) == 1
    assert transport.timeout_reports[0]["environment"] == "staging"
    assert transport.timeout_reports[0]["provider"] == "openai"
    client.close()


def test_preflight_500_fail_open_allows_provider_call() -> None:
    transport = FakeHttpClient({"error": "server"}, decision_status=500)  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    assert len(transport.unavailable_reports) == 1
    assert transport.unavailable_reports[0]["provider"] == "openai"
    client.close()


def test_preflight_500_fail_closed_blocks_provider_call() -> None:
    transport = FakeHttpClient({"error": "server"}, decision_status=500)  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    assert len(transport.unavailable_reports) == 1
    assert transport.unavailable_reports[0]["provider"] == "openai"
    client.close()


def test_preflight_invalid_json_fail_open_allows_provider_call() -> None:
    transport = FakeHttpClient({"invalid_json": True})  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    assert len(transport.unavailable_reports) == 1
    assert transport.unavailable_reports[0]["provider"] == "openai"
    client.close()


def test_preflight_invalid_json_fail_closed_blocks_provider_call() -> None:
    transport = FakeHttpClient({"invalid_json": True})  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    assert len(transport.unavailable_reports) == 1
    assert transport.unavailable_reports[0]["provider"] == "openai"
    client.close()


def test_anthropic_allow_path_calls_provider_and_emits_telemetry() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    anthropic_client, calls = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)

    anthropic_client.messages.create(
        model="claude-3-5-sonnet",
        max_tokens=128,
        messages=[{"role": "user", "content": "hello"}],
    )
    client.flush()
    assert len(calls) == 1
    assert len(transport.ingested_events) == 1
    assert transport.ingested_events[0]["provider"] == "anthropic"
    client.close()


def test_anthropic_block_path_prevents_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(  # type: ignore[arg-type]
            {
                "decision": "block",
                "reason": "tok_limit",
                "fail_mode": "open",
                "protect_decision_timeout_ms": 100,
            }
        ),
    )
    anthropic_client, calls = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)

    with pytest.raises(RHEONICBlockedError):
        anthropic_client.messages.create(
            model="claude-3-5-sonnet",
            max_tokens=128,
            messages=[{"role": "user", "content": "hello"}],
        )
    assert calls == []
    client.close()


def test_anthropic_includes_input_tokens_estimate() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    _set_anthropic_token_estimator_for_tests(lambda _payload: 444)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    anthropic_client, _ = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)

    anthropic_client.messages.create(
        model="claude-3-5-sonnet",
        max_tokens=128,
        messages=[{"role": "user", "content": "hello"}],
    )
    assert len(transport.decision_payloads) == 1
    assert transport.decision_payloads[0]["input_tokens_estimate"] == 444
    _set_anthropic_token_estimator_for_tests(None)
    client.close()


def test_google_allow_path_calls_provider_and_emits_telemetry() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    google_model, calls = _make_google_stub()
    instrument_google(google_model, client=client)

    google_model.generate_content("hello")
    client.flush()
    assert len(calls) == 1
    assert len(transport.ingested_events) == 1
    assert transport.ingested_events[0]["provider"] == "google"
    client.close()


def test_google_block_path_prevents_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(  # type: ignore[arg-type]
            {
                "decision": "block",
                "reason": "req_limit",
                "fail_mode": "open",
                "protect_decision_timeout_ms": 100,
            }
        ),
    )
    google_model, calls = _make_google_stub()
    instrument_google(google_model, client=client)

    with pytest.raises(RHEONICBlockedError):
        google_model.generate_content("hello")
    assert calls == []
    client.close()


def test_google_includes_input_tokens_estimate() -> None:
    transport = FakeHttpClient(  # type: ignore[arg-type]
        {
            "decision": "allow",
            "reason": "ok",
            "fail_mode": "open",
            "protect_decision_timeout_ms": 100,
        }
    )
    _set_google_token_estimator_for_tests(lambda _payload: 555)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    google_model, _ = _make_google_stub()
    instrument_google(google_model, client=client)

    google_model.generate_content("hello")
    assert len(transport.decision_payloads) == 1
    assert transport.decision_payloads[0]["input_tokens_estimate"] == 555
    _set_google_token_estimator_for_tests(None)
    client.close()


def test_provider_model_validation_accepts_openai_gpt_model() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient({"decision": "allow"}),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    client.close()


def test_provider_model_validation_accepts_anthropic_claude_model() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient({"decision": "allow"}),  # type: ignore[arg-type]
    )
    anthropic_client, calls = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)

    anthropic_client.messages.create(
        model="claude-3-5-sonnet",
        max_tokens=64,
        messages=[{"role": "user", "content": "hello"}],
    )
    assert len(calls) == 1
    client.close()


def test_provider_model_validation_accepts_google_model() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient({"decision": "allow"}),  # type: ignore[arg-type]
    )
    google_model, calls = _make_google_stub()
    instrument_google(google_model, client=client)

    google_model.generate_content("hello")
    assert len(calls) == 1
    client.close()


def test_provider_model_validation_does_not_enforce_prefixes() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient({"decision": "allow"}),  # type: ignore[arg-type]
    )
    anthropic_client, anthropic_calls = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)
    anthropic_client.messages.create(
        model="gpt-4o-mini",
        max_tokens=64,
        messages=[{"role": "user", "content": "hello"}],
    )

    google_model, google_calls = _make_google_stub()
    google_model.model_name = "claude-3-opus"
    instrument_google(google_model, client=client)
    google_model.generate_content("hello")

    assert len(anthropic_calls) == 1
    assert len(google_calls) == 1
    client.close()


def test_provider_model_validation_rejects_anthropic_call_when_model_missing() -> None:
    transport = FakeHttpClient({"decision": "allow"})  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    anthropic_client, calls = _make_anthropic_stub()
    instrument_anthropic(anthropic_client, client=client)

    with pytest.raises(RHEONICValidationError):
        anthropic_client.messages.create(
            max_tokens=64,
            messages=[{"role": "user", "content": "hello"}],
        )
    assert calls == []
    assert transport.decision_payloads == []
    client.close()


def test_provider_model_validation_rejects_openai_call_when_model_missing() -> None:
    transport = FakeHttpClient({"decision": "allow"})  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(RHEONICValidationError):
        openai_client.chat.completions.create(messages=[{"role": "user", "content": "hello"}], max_tokens=64)
    assert calls == []
    assert transport.decision_payloads == []
    client.close()


def test_provider_model_validation_rejects_google_call_when_model_missing() -> None:
    transport = FakeHttpClient({"decision": "allow"})  # type: ignore[arg-type]
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=transport,
    )
    google_model, calls = _make_google_stub()
    google_model.model_name = ""
    instrument_google(google_model, client=client)

    with pytest.raises(RHEONICValidationError):
        google_model.generate_content("hello")
    assert calls == []
    assert transport.decision_payloads == []
    client.close()


def test_provider_model_validation_rejects_missing_provider() -> None:
    with pytest.raises(RHEONICValidationError):
        validate_provider_model("", "any-model")


def test_provider_model_validation_rejects_unknown_provider() -> None:
    with pytest.raises(RHEONICValidationError):
        validate_provider_model("cohere", "command-r")


def test_protect_engine_bootstrap_ignores_non_success_and_updates_config_on_success() -> None:
    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=FakeHttpClient({}, decision_status=500),
    )
    engine.bootstrap()
    assert engine._fail_mode == "open"

    class BootstrapHttpClient(FakeHttpClient):
        def get(self, url: str, headers: dict[str, str] | None = None, **kwargs: Any) -> FakeResponse:
            _ = url, headers, kwargs
            return FakeResponse(
                200,
                {
                    "protect_fail_mode": "closed",
                    "protect_decision_timeout_ms": 321,
                },
            )

    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=BootstrapHttpClient({}),
    )
    engine.bootstrap()
    assert engine._fail_mode == "closed"
    assert engine._decision_timeout_ms == 321


def test_protect_engine_timeout_helpers_fall_back_across_transport_signatures() -> None:
    class TimeoutSOnlyClient:
        def post(self, url: str, json: dict[str, object], headers: dict[str, str], timeout_s: float) -> str:
            _ = url, json, headers
            return f"post:{timeout_s}"

        def get(self, url: str, headers: dict[str, str], timeout_s: float) -> str:
            _ = url, headers
            return f"get:{timeout_s}"

    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=TimeoutSOnlyClient(),
    )
    assert engine._post_with_timeout("http://localhost", {}, {}, 0.2) == "post:0.2"
    assert engine._get_with_timeout("http://localhost", {}, 0.3) == "get:0.3"

    class NoTimeoutClient:
        def post(self, url: str, json: dict[str, object], headers: dict[str, str]) -> str:
            _ = url, json, headers
            return "post:no-timeout"

        def get(self, url: str, headers: dict[str, str]) -> str:
            _ = url, headers
            return "get:no-timeout"

    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=NoTimeoutClient(),
    )
    assert engine._post_with_timeout("http://localhost", {}, {}, 0.2) == "post:no-timeout"
    assert engine._get_with_timeout("http://localhost", {}, 0.3) == "get:no-timeout"


def test_protect_engine_json_and_fallback_helpers_cover_invalid_shapes() -> None:
    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        fail_mode="closed",
        http_client=FakeHttpClient({}),
    )

    assert engine._parse_json_payload(object()) == {}
    assert engine._parse_json_payload(type("Response", (), {"json": lambda self: []})()) == {}
    assert engine._fallback_decision() == {"decision": "block", "reason": "decision_unavailable"}
    engine._fail_mode = "open"
    assert engine._fallback_decision() == {"decision": "allow", "reason": "decision_unavailable"}


def test_protect_engine_debug_uses_fallback_logger_when_debug_logger_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=FakeHttpClient({}),
        debug_logger=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    exceptions: list[str] = []
    debugs: list[tuple[str, object]] = []
    monkeypatch.setattr(protect_engine_module.logger, "exception", lambda message: exceptions.append(message))
    monkeypatch.setattr(
        protect_engine_module.logger, "debug", lambda message, extra=None: debugs.append((message, extra))
    )

    engine._debug("hello", provider="openai")

    assert exceptions == ["Protect engine debug logger failed"]
    assert debugs == [("hello", {"provider": "openai"})]


def test_parse_blocked_until_ms_handles_invalid_naive_and_zulu_values() -> None:
    assert _parse_blocked_until_ms(None) is None
    assert _parse_blocked_until_ms("") is None
    assert _parse_blocked_until_ms("not-a-date") is None
    assert _parse_blocked_until_ms("2026-03-22T00:00:00") is not None
    assert _parse_blocked_until_ms("2026-03-22T00:00:00Z") is not None


def test_is_timeout_error_handles_builtin_timeout() -> None:
    engine = ProtectEngine(
        base_url="http://localhost:8000",
        ingest_key="p1",
        environment="dev",
        request_timeout_s=0.5,
        http_client=FakeHttpClient({}),
    )
    try:
        raise TimeoutError("slow")
    except TimeoutError:
        assert engine._is_timeout_error() is True
