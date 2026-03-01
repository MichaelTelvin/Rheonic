# API tests for ingest key authentication behavior.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.v1.events import EventIn
from app.config import Settings
from app.dependencies import get_ingest_event_service, get_ingest_key_service, get_settings
from app.domain.models.ingest_key import IngestKey
from app.main import app
from app.security.ingest_keys import hash_key, last4


class FakeIngestService:
    # Test double for ingest service dependency.

    def __init__(self) -> None:
        self.ingested: list[object] = []

    def ingest(self, event: object) -> None:
        self.ingested.append(event)


class FakeIngestKeyService:
    # In-memory ingest key lookup service for endpoint auth tests.

    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        active_plaintext = "active-test-key"
        revoked_plaintext = "revoked-test-key"
        self._hash_to_project = {
            hash_key(active_plaintext): "p1",
        }
        self._revoked_hashes = {
            hash_key(revoked_plaintext),
        }
        self._records = [
            IngestKey(
                id="k-active",
                project_id="p1",
                name="dev",
                key_hash=hash_key(active_plaintext),
                last4=last4(active_plaintext),
                status="active",
                created_at=now,
                revoked_at=None,
            ),
            IngestKey(
                id="k-revoked",
                project_id="p1",
                name="old",
                key_hash=hash_key(revoked_plaintext),
                last4=last4(revoked_plaintext),
                status="revoked",
                created_at=now,
                revoked_at=now,
            ),
        ]
        _ = self._records
    def resolve_project_id(self, plaintext_key: str) -> str | None:
        key_hash = hash_key(plaintext_key)
        if key_hash in self._revoked_hashes:
            return None
        return self._hash_to_project.get(key_hash)


def _payload() -> dict[str, object]:
    # Build a minimal valid ingest payload.
    payload = EventIn(
        ts=datetime.now(timezone.utc),
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        response={"total_tokens": 10},
    )
    return payload.model_dump(mode="json")


def test_ingest_event_requires_ingest_key_header() -> None:
    # Missing ingest key must return 401.
    ingest_service = FakeIngestService()
    key_service = FakeIngestKeyService()
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_ingest_key_service] = lambda: key_service
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev")

    client = TestClient(app)
    response = client.post("/api/v1/events", json=_payload())

    assert response.status_code == 401
    assert response.json() == {"error": {"code": "unauthorized", "message": "missing ingest key"}}
    app.dependency_overrides.clear()


def test_ingest_event_rejects_invalid_and_revoked_key() -> None:
    # Invalid and revoked keys must return 401.
    ingest_service = FakeIngestService()
    key_service = FakeIngestKeyService()
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_ingest_key_service] = lambda: key_service
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev")
    client = TestClient(app)

    invalid = client.post(
        "/api/v1/events",
        json=_payload(),
        headers={"X-Project-Ingest-Key": "not-a-real-key"},
    )
    revoked = client.post(
        "/api/v1/events",
        json=_payload(),
        headers={"X-Project-Ingest-Key": "revoked-test-key"},
    )

    assert invalid.status_code == 401
    assert invalid.json() == {"error": {"code": "unauthorized", "message": "invalid ingest key"}}
    assert revoked.status_code == 401
    assert revoked.json() == {"error": {"code": "unauthorized", "message": "invalid ingest key"}}
    app.dependency_overrides.clear()


def test_ingest_event_accepts_active_key_and_maps_to_project() -> None:
    # Active key should resolve and map into event.project_id.
    ingest_service = FakeIngestService()
    key_service = FakeIngestKeyService()
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_ingest_key_service] = lambda: key_service
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev")
    client = TestClient(app)

    response = client.post(
        "/api/v1/events",
        json=_payload(),
        headers={"X-Project-Ingest-Key": "active-test-key"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert len(ingest_service.ingested) == 1
    assert getattr(ingest_service.ingested[0], "project_id") == "p1"
    app.dependency_overrides.clear()


def test_ingest_event_accepts_quoted_and_env_style_ingest_keys() -> None:
    # Pasted keys with quotes or env-var prefix should normalize and resolve.
    ingest_service = FakeIngestService()
    key_service = FakeIngestKeyService()
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_ingest_key_service] = lambda: key_service
    app.dependency_overrides[get_settings] = lambda: Settings(app_env="dev")
    client = TestClient(app)

    quoted = client.post(
        "/api/v1/events",
        json=_payload(),
        headers={"X-Project-Ingest-Key": "\"active-test-key\""},
    )
    assert quoted.status_code == 202

    env_style = client.post(
        "/api/v1/events",
        json=_payload(),
        headers={"X-Project-Ingest-Key": "LLMTBG_INGEST_KEY=active-test-key"},
    )
    assert env_style.status_code == 202
    assert len(ingest_service.ingested) == 2
    app.dependency_overrides.clear()
