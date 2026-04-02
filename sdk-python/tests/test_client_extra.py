from typing import Any

import pytest
from rheonic import client as client_module
from rheonic.client import Client, _SimpleResponse, _UrllibTransport, capture_event, create_client, get_default_client
from rheonic.protect_engine import RHEONICValidationError


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class RecordingHttpClient:
    def __init__(self, post_statuses: list[int] | None = None, fail_post: bool = False, fail_get: bool = False) -> None:
        self.post_statuses = list(post_statuses or [202])
        self.fail_post = fail_post
        self.fail_get = fail_get
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []
        self.closed = False

    def post(
        self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None
    ) -> FakeResponse:
        _ = timeout
        if self.fail_post:
            raise RuntimeError("post failed")
        self.posts.append({"url": url, "json": json, "headers": headers})
        status = self.post_statuses.pop(0) if self.post_statuses else 202
        return FakeResponse(status)

    def get(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> FakeResponse:
        _ = timeout
        if self.fail_get:
            raise RuntimeError("get failed")
        self.gets.append({"url": url, "headers": headers or {}})
        if url.endswith("/api/v1/protect/config"):
            return FakeResponse(200)
        return FakeResponse(200)

    def close(self) -> None:
        self.closed = True


def test_create_client_sets_default_client_and_module_capture_event_uses_it() -> None:
    fake_http = RecordingHttpClient()
    client = create_client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
    )
    client._http_client.close()
    client._http_client = fake_http
    client._protect_engine._http_client = fake_http  # type: ignore[attr-defined]

    capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}})
    client.flush(timeout_s=0.5)

    assert get_default_client() is client
    assert client.stats()["sent"] == 1
    client.close()


def test_drop_oldest_policy_keeps_newest_event() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=1,
        overflow_policy="drop_oldest",
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 1}})
    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 2}})
    client.flush(timeout_s=0.5)

    assert fake_http.posts[-1]["json"]["response"]["total_tokens"] == 2
    assert client.stats()["dropped"] == 1
    client.close()


def test_non_retryable_send_failure_increments_failed_counter() -> None:
    fake_http = RecordingHttpClient(post_statuses=[400])
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}})
    client.flush(timeout_s=0.5)

    assert client.stats()["failed"] == 1
    client.close()


def test_preflight_protect_decision_uses_fail_closed_fallback_on_unexpected_error() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="closed",
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client._protect_engine.evaluate = lambda _context: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    decision = client.preflight_protect_decision({"provider": "openai"})
    assert decision["decision"] == "block"
    assert decision["reason"] == "fail_closed"
    assert isinstance(decision["trace_id"], str) and decision["trace_id"]
    assert isinstance(decision["request_id"], str) and decision["request_id"]
    client.close()


def test_warm_connections_and_close_tolerate_transport_failures() -> None:
    fake_http = RecordingHttpClient(fail_get=True, fail_post=True)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=0.01,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.warm_connections()
    client.close()

    assert fake_http.closed is True


def test_create_client_closes_previous_default_client() -> None:
    first_http = RecordingHttpClient()
    first = create_client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
    )
    first._http_client.close()
    first._http_client = first_http
    first._protect_engine._http_client = first_http  # type: ignore[attr-defined]

    second_http = RecordingHttpClient()
    second = create_client(
        ingest_key="p2",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
    )
    second._http_client.close()
    second._http_client = second_http
    second._protect_engine._http_client = second_http  # type: ignore[attr-defined]

    assert first_http.closed is True
    assert get_default_client() is second
    second.close()


def test_capture_event_without_default_client_is_noop() -> None:
    client_module._default_client = None
    capture_event({"provider": "openai", "request": {}, "response": {}})
    assert get_default_client() is None


def test_capture_event_rejects_invalid_mapping() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    class BadMapping:
        def keys(self) -> list[str]:
            raise RuntimeError("boom")

    with pytest.raises(RHEONICValidationError):
        client.capture_event(BadMapping())  # type: ignore[arg-type]
    assert client.stats()["queued"] == 0
    client.close()


def test_capture_event_rejects_unknown_public_event_property() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    with pytest.raises(RHEONICValidationError):
        client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}, "extra": 1})
    assert client.stats()["queued"] == 0
    client.close()


def test_create_client_rejects_invalid_config() -> None:
    with pytest.raises(RHEONICValidationError):
        create_client(ingest_key="")

    with pytest.raises(RHEONICValidationError):
        Client(
            ingest_key="p1",
            base_url="http://localhost:8000",
            flush_interval_s=30.0,
            overflow_policy="wrong",  # type: ignore[arg-type]
        )


def test_flush_deadline_can_short_circuit_before_send() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
    )
    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}})
    client.flush(timeout_s=0.0)
    assert client.stats()["queued"] == 1
    client.close()


def test_close_is_idempotent() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
    )
    client.close()
    client.close()
    assert fake_http.closed is True


def test_debug_log_emits_with_and_without_metadata(monkeypatch: Any) -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=fake_http,  # type: ignore[arg-type]
        debug=True,
    )
    messages: list[dict[str, Any]] = []
    monkeypatch.setattr(
        client_module.logger,
        "debug",
        lambda message, extra=None, **kwargs: messages.append({"message": message, "extra": extra, "kwargs": kwargs}),
    )

    client.debug_log("plain message")
    client.debug_log("rich message", provider="openai", decision="warn")
    assert messages[0]["message"] == "plain message"
    assert messages[1]["extra"]["metadata"]["rendered"] == "decision=warn provider=openai"
    client.close()


def test_preflight_protect_decision_uses_fail_open_fallback_on_unexpected_error() -> None:
    fake_http = RecordingHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        protect_fail_mode="open",
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client._protect_engine.evaluate = lambda _context: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]

    decision = client.preflight_protect_decision({"provider": "openai"})
    assert decision["decision"] == "allow"
    assert decision["reason"] == "decision_unavailable"
    assert isinstance(decision["trace_id"], str) and decision["trace_id"]
    assert isinstance(decision["request_id"], str) and decision["request_id"]
    client.close()


def test_send_event_once_classifies_status_codes_and_exceptions() -> None:
    retry_http = RecordingHttpClient(post_statuses=[503])
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=retry_http,  # type: ignore[arg-type]
        debug=True,
    )
    assert client._send_event_once({"provider": "openai", "request": {}, "response": {}}) == (False, True)
    client.close()

    no_retry_http = RecordingHttpClient(post_statuses=[400])
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=no_retry_http,  # type: ignore[arg-type]
    )
    assert client._send_event_once({"provider": "openai", "request": {}, "response": {}}) == (False, False)
    client.close()

    failing_http = RecordingHttpClient(fail_post=True)
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=failing_http,  # type: ignore[arg-type]
        debug=True,
    )
    assert client._send_event_once({"provider": "openai", "request": {}, "response": {}}) == (False, True)
    client.close()


def test_send_event_counts_success_and_retry_exhaustion(monkeypatch: Any) -> None:
    monkeypatch.setattr(client_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(client_module.random, "uniform", lambda _a, _b: 0.0)

    success_http = RecordingHttpClient(post_statuses=[202])
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=success_http,  # type: ignore[arg-type]
    )
    client._send_event({"provider": "openai", "request": {}, "response": {}})
    assert client.stats()["sent"] == 1
    client.close()

    failed_http = RecordingHttpClient(post_statuses=[503, 503])
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        http_client=failed_http,  # type: ignore[arg-type]
    )
    client._send_event({"provider": "openai", "request": {}, "response": {}})
    assert client.stats()["failed"] == 1
    client.close()


def test_urllib_transport_maps_success_and_http_error(monkeypatch: Any) -> None:
    class ResponseContext:
        def __init__(self, code: int) -> None:
            self._code = code

        def __enter__(self) -> "ResponseContext":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        def getcode(self) -> int:
            return self._code

    monkeypatch.setattr(client_module.request, "urlopen", lambda _payload, timeout=None: ResponseContext(204))
    transport = _UrllibTransport(timeout_s=1.0)
    assert transport.post("http://localhost", {}, {}).status_code == 204
    assert transport.get("http://localhost").status_code == 204

    def _raise_http_error(_payload: Any, timeout: Any = None) -> Any:
        _ = timeout
        raise client_module.error.HTTPError("http://localhost", 418, "teapot", hdrs=None, fp=None)

    monkeypatch.setattr(client_module.request, "urlopen", _raise_http_error)
    assert transport.post("http://localhost", {}, {}).status_code == 418
    assert transport.get("http://localhost").status_code == 418


def test_simple_response_exposes_status_code() -> None:
    assert _SimpleResponse(201).status_code == 201
