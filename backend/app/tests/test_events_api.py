# Unit tests for ingest endpoint header behavior.
from datetime import datetime, timezone

from fastapi import HTTPException

from app.api.v1.events import EventIn, ingest_event


class FakeIngestService:
    # Test double for ingest service dependency.

    def __init__(self) -> None:
        self.ingested: list[object] = []

    def ingest(self, event: object) -> None:
        self.ingested.append(event)


def _payload() -> EventIn:
    # Build a minimal valid ingest payload.
    return EventIn(
        ts=datetime.now(timezone.utc),
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        response={"total_tokens": 10},
    )


def test_ingest_event_requires_ingest_key_header() -> None:
    # Missing ingest key must return 401.
    service = FakeIngestService()

    try:
        ingest_event(payload=_payload(), service=service, ingest_key=None)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "missing ingest key"


def test_ingest_event_maps_ingest_key_to_project_id() -> None:
    # Ingest key should be mapped into event.project_id for persistence.
    service = FakeIngestService()

    response = ingest_event(payload=_payload(), service=service, ingest_key="p1-key")

    assert response == {"status": "accepted"}
    assert len(service.ingested) == 1
    assert getattr(service.ingested[0], "project_id") == "p1-key"
