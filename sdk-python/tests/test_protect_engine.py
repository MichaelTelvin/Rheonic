# Tests for always-on protect preflight behavior in OpenAI instrumentation.
from typing import Any

import pytest

from llmtokenburnguard.client import Client
from llmtokenburnguard.protect_engine import LLMTBGBlockedError
from llmtokenburnguard.providers.openai_adapter import instrument_openai


class FakeResponse:
    # Minimal response object for SDK transport tests.

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHttpClient:
    # Fake HTTP transport that routes protect decisions and ingest calls.

    def __init__(self, decision: dict[str, Any] | Exception) -> None:
        self.decision = decision
        self.calls: list[str] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], **kwargs: Any) -> FakeResponse:
        _ = json
        _ = headers
        _ = kwargs
        self.calls.append(url)
        if url.endswith("/api/v1/protect/decision"):
            if isinstance(self.decision, Exception):
                raise self.decision
            return FakeResponse(status_code=200, payload=self.decision)
        return FakeResponse(status_code=202, payload={"status": "accepted"})

    def close(self) -> None:
        return


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


def test_preflight_warn_allows_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(  # type: ignore[arg-type]
            {
                "decision": "warn",
                "reason": "incident_medium",
                "fail_mode": "open",
                "protect_decision_timeout_ms": 100,
            }
        ),
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    client.close()


def test_preflight_timeout_fail_open_allows_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=FakeHttpClient(TimeoutError("timeout")),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    openai_client.chat.completions.create(model="gpt-4o-mini")
    assert len(calls) == 1
    client.close()


def test_preflight_timeout_fail_closed_blocks_provider_call() -> None:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=FakeHttpClient(TimeoutError("timeout")),  # type: ignore[arg-type]
    )
    openai_client, calls = _make_openai_stub()
    instrument_openai(openai_client, client=client)

    with pytest.raises(LLMTBGBlockedError):
        openai_client.chat.completions.create(model="gpt-4o-mini")
    assert calls == []
    client.close()
