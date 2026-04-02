import asyncio
from typing import Any

import pytest
from rheonic.client import Client
from rheonic.protect_engine import RHEONICBlockedError, RHEONICValidationError
from rheonic.providers.anthropic_adapter import instrument_anthropic
from rheonic.providers.google_adapter import instrument_google
from rheonic.providers.openai_adapter import instrument_openai


class FakeHttpClient:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None) -> Any:
        _ = headers
        _ = timeout
        self.posts.append({"url": url, "json": json})
        return type("Response", (), {"status_code": 202})()

    def get(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        _ = headers
        _ = timeout
        return type("Response", (), {"status_code": 200})()

    def close(self) -> None:
        return


def _client_with_decision(decision: dict[str, object]) -> Client:
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=FakeHttpClient(),  # type: ignore[arg-type]
    )
    client.preflight_protect_decision = lambda _context: decision  # type: ignore[method-assign]
    return client


def test_openai_clamp_applies_recommended_max_tokens_and_marks_applied() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 32, "applied": False},
        }
    )
    calls: list[dict[str, Any]] = []

    class _Completions:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            usage = type("Usage", (), {"total_tokens": 12})()
            return type("Response", (), {"model": "gpt-4o-mini", "usage": usage})()

    openai = type("OpenAI", (), {"chat": type("Chat", (), {"completions": _Completions()})()})()
    import rheonic.providers.openai_adapter as openai_adapter

    openai_adapter._set_token_estimator_for_tests(lambda _payload: 91)
    instrument_openai(openai, client=client)

    openai.chat.completions.create(model="gpt-4o-mini", max_tokens=128)

    assert calls[0]["max_tokens"] == 32
    client.flush(timeout_s=0.5)
    fake_http = client._http_client
    assert fake_http.posts[-1]["json"]["request"]["token_explosion_tokens"] == 91
    assert fake_http.posts[-1]["json"]["request"]["input_tokens_estimate"] == 91
    openai_adapter._set_token_estimator_for_tests(None)
    client.close()


def test_openai_failure_capture_reads_http_status_from_exception_response() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    class _Response:
        status_code = 429

    class _OpenAIError(RuntimeError):
        response = _Response()

    class _Completions:
        def create(self, **kwargs: Any) -> Any:
            _ = kwargs
            raise _OpenAIError("boom")

    openai = type("OpenAI", (), {"chat": type("Chat", (), {"completions": _Completions()})()})()
    instrument_openai(openai, client=client)

    with pytest.raises(_OpenAIError):
        openai.chat.completions.create(model="gpt-4o-mini")

    client.flush(timeout_s=0.5)
    assert client.stats()["sent"] == 1
    client.close()


def test_openai_async_wrapper_supports_success_and_clamp() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 12, "applied": False},
        }
    )
    calls: list[dict[str, Any]] = []

    class _Completions:
        async def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            usage = type("Usage", (), {"total_tokens": 22})()
            return type("Response", (), {"model": "gpt-4o-mini", "usage": usage})()

    openai = type("OpenAI", (), {"chat": type("Chat", (), {"completions": _Completions()})()})()
    instrument_openai(openai, client=client)

    asyncio.run(openai.chat.completions.create(model="gpt-4o-mini", max_tokens=40))
    assert calls[0]["max_tokens"] == 12
    client.close()


def test_openai_async_wrapper_captures_failure() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    class _Response:
        status_code = 500

    class _OpenAIError(RuntimeError):
        response = _Response()

    class _Completions:
        async def create(self, **kwargs: Any) -> Any:
            _ = kwargs
            raise _OpenAIError("boom")

    openai = type("OpenAI", (), {"chat": type("Chat", (), {"completions": _Completions()})()})()
    instrument_openai(openai, client=client)

    with pytest.raises(_OpenAIError):
        asyncio.run(openai.chat.completions.create(model="gpt-4o-mini"))

    client.flush(timeout_s=0.5)
    assert client.stats()["sent"] == 1
    client.close()


def test_openai_instrumentation_rejects_invalid_client_shape() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    with pytest.raises(RHEONICValidationError):
        instrument_openai(object(), client=client)
    client.close()


def test_anthropic_async_wrapper_blocks_and_supports_clamp() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 10, "applied": False},
        }
    )
    calls: list[dict[str, Any]] = []

    class _Messages:
        async def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            usage = type("Usage", (), {"input_tokens": 4, "output_tokens": 6})()
            return type("Response", (), {"model": "claude-3-5-sonnet", "usage": usage})()

    anthropic = type("Anthropic", (), {"messages": _Messages()})()
    instrument_anthropic(anthropic, client=client)

    asyncio.run(anthropic.messages.create(model="claude-3-5-sonnet", max_tokens=40))
    assert calls[0]["max_tokens"] == 10
    client.close()


def test_anthropic_block_raises_blocked_error() -> None:
    client = _client_with_decision(
        {
            "decision": "block",
            "reason": "tok_limit",
            "trace_id": "trace-test",
            "request_id": "request-test",
            "retry_after_seconds": 60,
        }
    )

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            _ = kwargs
            return object()

    anthropic = type("Anthropic", (), {"messages": _Messages()})()
    instrument_anthropic(anthropic, client=client)

    with pytest.raises(RHEONICBlockedError) as exc_info:
        anthropic.messages.create(model="claude-3-5-sonnet")
    assert exc_info.value.reason == "tok_limit"
    assert exc_info.value.trace_id == "trace-test"
    assert exc_info.value.request_id == "request-test"
    assert exc_info.value.retry_after_seconds == 60
    client.close()


def test_anthropic_instrumentation_rejects_invalid_client_shape() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    with pytest.raises(RHEONICValidationError):
        instrument_anthropic(object(), client=client)
    client.close()


def test_google_clamp_inserts_generation_config_and_extracts_nested_usage() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 15, "applied": False},
        }
    )
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _Usage:
        prompt_token_count = 3
        candidates_token_count = 7

    class _NestedResponse:
        usage_metadata = _Usage()

    class _GoogleModel:
        model_name = "gemini-1.5-pro"

        def generate_content(self, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return type("Response", (), {"response": _NestedResponse()})()

    google = _GoogleModel()
    instrument_google(google, client=client)

    google.generate_content({"prompt": "hi"})
    payload = calls[0][0][0]
    assert payload["generation_config"]["max_output_tokens"] == 15
    client.close()


def test_google_async_wrapper_supports_success_and_clamp() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 9, "applied": False},
        }
    )
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _GoogleModel:
        model_name = "gemini-1.5-pro"

        async def generate_content(self, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            usage_metadata = type("Usage", (), {"total_token_count": 14})()
            return type("Response", (), {"usage_metadata": usage_metadata})()

    google = _GoogleModel()
    instrument_google(google, client=client)

    asyncio.run(google.generate_content({"prompt": "hi"}))
    payload = calls[0][0][0]
    assert payload["generation_config"]["max_output_tokens"] == 9
    client.close()


def test_google_wrapper_supports_current_genai_client_shape() -> None:
    client = _client_with_decision(
        {
            "decision": "clamp",
            "reason": "token_clamp",
            "apply_clamp_enabled": True,
            "clamp": {"recommended_max_output_tokens": 12, "applied": False},
        }
    )
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    class _Config:
        def __init__(self, max_output_tokens: int) -> None:
            self.max_output_tokens = max_output_tokens

    class _Models:
        def generate_content(self, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            usage_metadata = type("Usage", (), {"total_token_count": 14})()
            return type("Response", (), {"usage_metadata": usage_metadata})()

    google = type("GoogleClient", (), {"models": _Models()})()
    instrument_google(google, client=client)

    google.models.generate_content(
        model="gemini-1.5-pro",
        contents="hi",
        config=_Config(max_output_tokens=30),
    )
    assert calls[0][1]["config"].max_output_tokens == 12
    client.close()


def test_google_async_wrapper_captures_failure() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    class _Response:
        status_code = 503

    class _GoogleError(RuntimeError):
        response = _Response()

    class _GoogleModel:
        model_name = "gemini-1.5-pro"

        async def generate_content(self, *args: Any, **kwargs: Any) -> Any:
            _ = args, kwargs
            raise _GoogleError("boom")

    google = _GoogleModel()
    instrument_google(google, client=client)

    with pytest.raises(_GoogleError):
        asyncio.run(google.generate_content("hi"))

    client.flush(timeout_s=0.5)
    assert client.stats()["sent"] == 1
    client.close()


def test_google_instrumentation_rejects_invalid_client_shape() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    with pytest.raises(RHEONICValidationError):
        instrument_google(object(), client=client)
    client.close()


def test_anthropic_async_wrapper_captures_failure() -> None:
    client = _client_with_decision({"decision": "allow", "reason": "ok"})

    class _Response:
        status_code = 429

    class _AnthropicError(RuntimeError):
        response = _Response()

    class _Messages:
        async def create(self, **kwargs: Any) -> Any:
            _ = kwargs
            raise _AnthropicError("boom")

    anthropic_client = type("Anthropic", (), {"messages": _Messages()})()
    instrument_anthropic(anthropic_client, client=client)

    with pytest.raises(_AnthropicError):
        asyncio.run(anthropic_client.messages.create(model="claude-3-5-sonnet", max_tokens=12))

    client.flush(timeout_s=0.5)
    assert client.stats()["sent"] == 1
    client.close()
