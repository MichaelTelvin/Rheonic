# Unit tests for SDK async client queue behavior.
from typing import Any

from rheonic.client import Client


class FakeHttpClient:
    # Minimal fake HTTP transport for client tests.

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> None:
        self.calls.append({"url": url, "json": json, "headers": headers})

    def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        self.calls.append({"url": url, "headers": headers or {}, "method": "GET"})
        return type("Response", (), {"status_code": 200})()

    def close(self) -> None:
        return


class FlakyHttpClient:
    # Fails first attempt with 5xx, then succeeds.

    def __init__(self) -> None:
        self.calls = 0

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        self.calls += 1
        if self.calls == 1:
            return type("Response", (), {"status_code": 503})()
        return type("Response", (), {"status_code": 200})()

    def get(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return type("Response", (), {"status_code": 200})()

    def close(self) -> None:
        return


def test_client_flush_sends_header_and_payload() -> None:
    # Flush should send queued events with ingest-key header.
    fake_http = FakeHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=10,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}})
    client.flush(timeout_s=0.5)
    client.close()

    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["headers"]["X-Project-Ingest-Key"] == "p1"


def test_queue_overflow_drop_newest_policy() -> None:
    # Queue should keep oldest event when overflow policy is drop_newest.
    fake_http = FakeHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=1,
        overflow_policy="drop_newest",
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 1}})
    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 2}})
    client.flush(timeout_s=0.5)
    client.close()

    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["json"]["response"]["total_tokens"] == 1
    assert client.stats()["dropped"] == 1


def test_retry_runs_exactly_once_for_transient_failure() -> None:
    # One retry should occur for 5xx before succeeding.
    flaky_http = FlakyHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=10,
        http_client=flaky_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {}})
    client.flush(timeout_s=1.0)
    stats = client.stats()
    client.close()

    assert flaky_http.calls == 2
    assert stats["sent"] == 1
    assert stats["failed"] == 0


def test_warm_connections_hits_health_endpoint() -> None:
    fake_http = FakeHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=10,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.warm_connections()
    client.close()

    get_calls = [call for call in fake_http.calls if call.get("method") == "GET"]
    assert len(get_calls) == 1
    assert get_calls[0]["url"] == "http://localhost:8000/health"
