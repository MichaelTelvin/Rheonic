# Tests for always-on protect preflight behavior in OpenAI instrumentation.
import time
from typing import Any

import pytest

from llmtokenburnguard.client import Client
from llmtokenburnguard.protect_engine import LLMTBGBlockedError
from llmtokenburnguard.providers.openai_adapter import instrument_openai, _set_token_estimator_for_tests


class FakeResponse:
    # Minimal response object for SDK transport tests.

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None, json_error: Exception | None = None) -> None:
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

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], **kwargs: Any) -> FakeResponse:
        _ = headers
        _ = kwargs
        self.calls.append(url)
        if url.endswith("/api/v1/protect/decision-timeout"):
            self.timeout_reports.append(json)
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

    with pytest.raises(LLMTBGBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
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
                "reason": "predictive_near_cap",
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
            "reason": "incident_medium",
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
    assert request_payload.get("protect_reason") == "incident_medium"
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

    with pytest.raises(LLMTBGBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    _wait_for_timeout_reports(transport, expected=1)
    assert len(transport.timeout_reports) == 1
    assert transport.timeout_reports[0]["environment"] == "staging"
    client.close()


def test_preflight_500_fail_open_allows_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=FakeHttpClient({"error": "server"}, decision_status=500),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    client.close()


def test_preflight_500_fail_closed_blocks_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=FakeHttpClient({"error": "server"}, decision_status=500),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(LLMTBGBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    client.close()


def test_preflight_invalid_json_fail_open_allows_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=FakeHttpClient({"invalid_json": True}),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    client.close()


def test_preflight_invalid_json_fail_closed_blocks_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=FakeHttpClient({"invalid_json": True}),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(LLMTBGBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    client.close()
