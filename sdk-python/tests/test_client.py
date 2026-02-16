# Unit tests for SDK async client queue behavior.
from typing import Any

from llmtokenburnguard.client import Client


class FakeHttpClient:
    # Minimal fake HTTP transport for client tests.

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> None:
        self.calls.append({"url": url, "json": json, "headers": headers})


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


def test_client_drops_when_queue_is_full() -> None:
    # Queue should drop new events when max size is reached.
    fake_http = FakeHttpClient()
    client = Client(
        ingest_key="p1",
        base_url="http://localhost:8000",
        flush_interval_s=30.0,
        max_queue_size=1,
        http_client=fake_http,  # type: ignore[arg-type]
    )

    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 1}})
    client.capture_event({"provider": "openai", "environment": "dev", "request": {}, "response": {"total_tokens": 2}})
    client.flush(timeout_s=0.5)
    client.close()

    assert len(fake_http.calls) == 1
    assert fake_http.calls[0]["json"]["response"]["total_tokens"] == 1
