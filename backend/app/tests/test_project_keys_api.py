# API tests for project and ingest key management endpoints.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_ingest_event_service, get_ingest_key_service, get_project_service
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, EventRecord, IncidentRecord, IngestKeyRecord, ProjectModelRecord, ProjectRecord
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


def _make_client(tmp_path, current_user: User | None = None) -> tuple[TestClient, DatabaseSessionFactory, FakeIngestService]:
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
    app.dependency_overrides[get_current_user] = lambda: current_user or User(
        id="u1",
        email="u1@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
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
    assert duplicate.json() == {"error": {"code": "conflict", "message": "project name already exists"}}
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
    assert revoked_ingest.json() == {"error": {"code": "unauthorized", "message": "invalid ingest key"}}

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


def test_key_routes_are_scoped_to_project_owner(tmp_path) -> None:
    # A user cannot manage keys for another user's project.
    owner = User(
        id="u1",
        email="u1@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    client, _, _ = _make_client(tmp_path, current_user=owner)
    project = client.post("/api/v1/projects", json={"name": "Owner Project"}).json()
    project_id = project["id"]

    other_user = User(
        id="u2",
        email="u2@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_current_user] = lambda: other_user

    list_response = client.get(f"/api/v1/projects/{project_id}/keys")
    create_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "prod"})
    assert list_response.status_code == 404
    assert create_response.status_code == 404
    _cleanup_overrides()


def test_project_providers_endpoint_returns_sorted_distinct_values(tmp_path) -> None:
    # Providers endpoint should return de-duplicated sorted providers for one project.
    client, session_factory, _ = _make_client(tmp_path)
    project = client.post("/api/v1/projects", json={"name": "Provider List Project"}).json()
    project_id = project["id"]

    with session_factory.create_session() as session:
        session.add_all(
            [
                ProjectModelRecord(
                    id="pm-1",
                    project_id=project_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    first_seen_at=datetime.now(timezone.utc),
                ),
                ProjectModelRecord(
                    id="pm-2",
                    project_id=project_id,
                    provider="openai",
                    model="gpt-4.1",
                    first_seen_at=datetime.now(timezone.utc),
                ),
                ProjectModelRecord(
                    id="pm-3",
                    project_id=project_id,
                    provider="anthropic",
                    model="claude-3-5-sonnet",
                    first_seen_at=datetime.now(timezone.utc),
                ),
            ]
        )
        session.commit()

    response = client.get(f"/api/v1/projects/{project_id}/providers")
    assert response.status_code == 200
    assert response.json() == {"providers": ["anthropic", "openai"]}
    _cleanup_overrides()


def test_project_providers_endpoint_returns_empty_list_when_none_seen(tmp_path) -> None:
    # Providers endpoint should return an empty list for projects without recorded models.
    client, _, _ = _make_client(tmp_path)
    project = client.post("/api/v1/projects", json={"name": "No Providers Yet"}).json()
    project_id = project["id"]

    response = client.get(f"/api/v1/projects/{project_id}/providers")
    assert response.status_code == 200
    assert response.json() == {"providers": []}
    _cleanup_overrides()


def test_project_delete_cascades_all_scoped_data_and_keeps_other_projects(tmp_path) -> None:
    # Deleting one project should remove all scoped rows and keep sibling project data intact.
    client, session_factory, _ = _make_client(tmp_path)
    target = client.post("/api/v1/projects", json={"name": "Delete Target"}).json()
    survivor = client.post("/api/v1/projects", json={"name": "Delete Survivor"}).json()
    target_id = target["id"]
    survivor_id = survivor["id"]
    now = datetime.now(timezone.utc)

    # Create API keys for both projects so ingest-key artifacts exist.
    target_key = client.post(f"/api/v1/projects/{target_id}/keys", json={"name": "target-key"})
    survivor_key = client.post(f"/api/v1/projects/{survivor_id}/keys", json={"name": "survivor-key"})
    assert target_key.status_code == 200
    assert survivor_key.status_code == 200

    # Persist protect and webhook settings so project config artifacts are present.
    protect_target = client.put(
        f"/api/v1/projects/{target_id}/protect",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "closed",
            "apply_clamp": True,
            "protect_max_req_per_min": 120,
            "protect_max_tok_per_min": 48000,
            "protect_decision_timeout_ms": 150,
        },
    )
    protect_survivor = client.put(
        f"/api/v1/projects/{survivor_id}/protect",
        json={
            "protect_enabled": False,
            "protect_fail_mode": "open",
            "apply_clamp": False,
            "protect_max_req_per_min": 25,
            "protect_max_tok_per_min": 5000,
            "protect_decision_timeout_ms": 100,
        },
    )
    webhook_target = client.put(
        f"/api/v1/projects/{target_id}/webhook",
        json={
            "enabled": True,
            "email_enabled": True,
            "url": "https://example.com/webhook-target",
            "secret": "target-secret",
        },
    )
    webhook_survivor = client.put(
        f"/api/v1/projects/{survivor_id}/webhook",
        json={
            "enabled": True,
            "email_enabled": False,
            "url": "https://example.com/webhook-survivor",
            "secret": "survivor-secret",
        },
    )
    assert protect_target.status_code == 200
    assert protect_survivor.status_code == 200
    assert webhook_target.status_code == 200
    assert webhook_survivor.status_code == 200

    # Add telemetry/incidents/provider-model rows for both projects.
    with session_factory.create_session() as session:
        session.add_all(
            [
                EventRecord(
                    id="evt-target",
                    ts=now,
                    project_id=target_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    environment="dev",
                    input_tokens=12,
                    output_tokens=24,
                    total_tokens=36,
                    status="ok",
                ),
                EventRecord(
                    id="evt-survivor",
                    ts=now,
                    project_id=survivor_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    environment="prod",
                    input_tokens=8,
                    output_tokens=16,
                    total_tokens=24,
                    status="ok",
                ),
                IncidentRecord(
                    id="inc-target",
                    project_id=target_id,
                    provider="openai",
                    type="near_cap",
                    status="open",
                    fingerprint="fp-target",
                    evidence={"detail": "target"},
                    created_at=now,
                    last_seen_at=now,
                ),
                IncidentRecord(
                    id="inc-survivor",
                    project_id=survivor_id,
                    provider="openai",
                    type="near_cap",
                    status="open",
                    fingerprint="fp-survivor",
                    evidence={"detail": "survivor"},
                    created_at=now,
                    last_seen_at=now,
                ),
                ProjectModelRecord(
                    id="pm-target",
                    project_id=target_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    first_seen_at=now,
                ),
                ProjectModelRecord(
                    id="pm-survivor",
                    project_id=survivor_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    first_seen_at=now,
                ),
            ]
        )
        session.commit()

    deleted = client.delete(f"/api/v1/projects/{target_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}

    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    assert all(item["id"] != target_id for item in listed.json())
    assert any(item["id"] == survivor_id for item in listed.json())

    with session_factory.create_session() as session:
        assert session.query(ProjectRecord).filter(ProjectRecord.id == target_id).count() == 0
        assert session.query(EventRecord).filter(EventRecord.project_id == target_id).count() == 0
        assert session.query(IncidentRecord).filter(IncidentRecord.project_id == target_id).count() == 0
        assert session.query(IngestKeyRecord).filter(IngestKeyRecord.project_id == target_id).count() == 0
        assert session.query(ProjectModelRecord).filter(ProjectModelRecord.project_id == target_id).count() == 0

        # Ensure sibling project data still exists.
        assert session.query(ProjectRecord).filter(ProjectRecord.id == survivor_id).count() == 1
        assert session.query(EventRecord).filter(EventRecord.project_id == survivor_id).count() == 1
        assert session.query(IncidentRecord).filter(IncidentRecord.project_id == survivor_id).count() == 1
        assert session.query(IngestKeyRecord).filter(IngestKeyRecord.project_id == survivor_id).count() == 1
        assert session.query(ProjectModelRecord).filter(ProjectModelRecord.project_id == survivor_id).count() == 1

    deleted_project_protect = client.get(f"/api/v1/projects/{target_id}/protect")
    deleted_project_webhook = client.get(f"/api/v1/projects/{target_id}/webhook")
    deleted_project_keys = client.get(f"/api/v1/projects/{target_id}/keys")
    assert deleted_project_protect.status_code == 404
    assert deleted_project_webhook.status_code == 404
    assert deleted_project_keys.status_code == 404
    _cleanup_overrides()
