# API tests for project and ingest key management endpoints.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.config import Settings
from app.dependencies import get_ingest_event_service, get_ingest_key_service, get_project_service, get_settings
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, IngestKeyRecord
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.main import app
from app.security.ingest_keys import hash_key


class FakeIngestService:
    # Test double for ingest service dependency.

    def __init__(self) -> None:
        self.ingested: list[object] = []

    def ingest(self, event: object) -> None:
        self.ingested.append(event)


def _make_client(tmp_path, app_env: str = "dev") -> tuple[TestClient, DatabaseSessionFactory, FakeIngestService]:
    # Build app client with real project/key services against temporary sqlite DB.
    db_url = f"sqlite:///{tmp_path}/api_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    project_service = ProjectService(ProjectRepositoryImpl(session_factory=session_factory))
    ingest_key_service = IngestKeyService(
        ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
        project_repository=ProjectRepositoryImpl(session_factory=session_factory),
    )
    ingest_service = FakeIngestService()

    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_ingest_key_service] = lambda: ingest_key_service
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_settings] = lambda: Settings(app_env=app_env)
    return TestClient(app), session_factory, ingest_service


def _cleanup_overrides() -> None:
    # Clear dependency overrides after each test.
    app.dependency_overrides.clear()


def _event_payload() -> dict[str, object]:
    # Build a minimal valid ingest payload.
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "environment": "dev",
        "response": {"total_tokens": 10},
    }


def test_project_create_duplicate_and_list(tmp_path) -> None:
    # Project endpoint should create, reject duplicate names, and list projects.
    client, _, _ = _make_client(tmp_path)

    created = client.post("/api/v1/projects", json={"name": "Demo"})
    duplicate = client.post("/api/v1/projects", json={"name": "Demo"})
    listed = client.get("/api/v1/projects")

    assert created.status_code == 200
    assert created.json()["name"] == "Demo"
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "project name already exists"}
    assert any(item["name"] == "Demo" for item in listed.json())
    _cleanup_overrides()


def test_key_create_list_revoke_rotate_and_ingest_mapping(tmp_path) -> None:
    # Key endpoints should return plaintext once, revoke/rotate, and enforce ingest mapping.
    client, session_factory, ingest_service = _make_client(tmp_path)

    project = client.post("/api/v1/projects", json={"name": "Key Test"}).json()
    project_id = project["id"]

    created = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "dev"})
    assert created.status_code == 200
    create_body = created.json()
    plaintext_key = create_body["key"]
    key_id = create_body["key_id"]
    assert len(plaintext_key) >= 32

    with session_factory.create_session() as session:
        stored = session.query(IngestKeyRecord).filter(IngestKeyRecord.id == key_id).first()
        assert stored is not None
        assert stored.key_hash == hash_key(plaintext_key)
        assert stored.key_hash != plaintext_key
        assert stored.last4 == plaintext_key[-4:]

    listed = client.get(f"/api/v1/projects/{project_id}/keys")
    assert listed.status_code == 200
    key_items = listed.json()
    assert len(key_items) == 1
    assert "key" not in key_items[0]

    active_ingest = client.post(
        "/api/v1/events",
        json=_event_payload(),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert active_ingest.status_code == 202
    assert len(ingest_service.ingested) == 1
    assert getattr(ingest_service.ingested[0], "project_id") == project_id

    revoked = client.post(f"/api/v1/keys/{key_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    revoked_ingest = client.post(
        "/api/v1/events",
        json=_event_payload(),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert revoked_ingest.status_code == 401
    assert revoked_ingest.json() == {"detail": "invalid ingest key"}

    rotated = client.post(f"/api/v1/keys/{key_id}/rotate")
    assert rotated.status_code == 200
    new_plaintext = rotated.json()["key"]
    assert new_plaintext != plaintext_key

    rotated_ingest = client.post(
        "/api/v1/events",
        json=_event_payload(),
        headers={"X-Project-Ingest-Key": new_plaintext},
    )
    assert rotated_ingest.status_code == 202
    _cleanup_overrides()


def test_management_endpoints_blocked_when_not_dev(tmp_path) -> None:
    # Mutating management endpoints should be blocked outside dev mode.
    client, _, _ = _make_client(tmp_path, app_env="prod")

    create_project = client.post("/api/v1/projects", json={"name": "Prod Blocked"})
    assert create_project.status_code == 403
    assert create_project.json() == {"detail": "not enabled"}

    project_list = client.get("/api/v1/projects")
    assert project_list.status_code == 200

    # ids are placeholders since request should be blocked before lookup
    create_key = client.post("/api/v1/projects/p1/keys", json={"name": "prod"})
    revoke = client.post("/api/v1/keys/k1/revoke")
    rotate = client.post("/api/v1/keys/k1/rotate")
    assert create_key.status_code == 403
    assert revoke.status_code == 403
    assert rotate.status_code == 403
    _cleanup_overrides()
