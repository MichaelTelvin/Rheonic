from typing import Any

from rheonic.client import Client, capture_event, create_client, get_default_client


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

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str], timeout: float | None = None) -> FakeResponse:
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

    assert client.preflight_protect_decision({"provider": "openai"}) == {
        "decision": "block",
        "reason": "decision_unavailable",
    }
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
