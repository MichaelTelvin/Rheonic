from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.application.services.project_service import ProjectService
from app.dependencies import get_current_user, get_project_service, get_transport_outbox_repository, get_webhook_dispatcher
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, TransportOutboxRecord
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.db.repositories.transport_outbox_repository_impl import TransportOutboxRepositoryImpl
from app.main import app


class FakeWebhookDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str, str | None, str | None, bool]] = []

    def enqueue(
        self,
        project_id: str,
        payload: dict[str, object],
        event_type: str,
        *,
        override_url: str | None = None,
        override_payload_template_json: str | None = None,
        force_send: bool = False,
    ) -> None:
        self.calls.append(
            (
                project_id,
                payload,
                event_type,
                override_url,
                override_payload_template_json,
                force_send,
            )
        )


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


def _make_client(tmp_path, current_user: User | None = None) -> tuple[TestClient, FakeWebhookDispatcher]:
    db_url = f"sqlite:///{tmp_path}/webhook_api_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    service = ProjectService(project_repository=ProjectRepositoryImpl(session_factory=session_factory))
    dispatcher = FakeWebhookDispatcher()

    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[get_webhook_dispatcher] = lambda: dispatcher
    app.dependency_overrides[get_transport_outbox_repository] = lambda: TransportOutboxRepositoryImpl(session_factory=session_factory)
    app.dependency_overrides[get_current_user] = lambda: current_user or User(
        id="u1",
        email="u1@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    return TestClient(app), dispatcher


def _set_protect_enabled(client: TestClient, project_id: str) -> None:
    response = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "apply_clamp": False,
            "protect_max_req_per_min": None,
            "protect_max_tok_per_min": None,
        },
    )
    assert response.status_code == 200


def test_project_webhook_owner_get_put_and_test(tmp_path) -> None:
    client, dispatcher = _make_client(tmp_path)
    project = client.post("/api/v1/projects", json={"name": "Webhook Demo"}).json()
    project_id = project["id"]
    _set_protect_enabled(client, project_id)

    put_response = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={
            "enabled": True,
            "url": "https://example.test/hook",
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["enabled"] is True

    get_response = client.get(f"/api/v1/projects/{project_id}/webhook")
    assert get_response.status_code == 200
    assert get_response.json()["url"] == "https://example.test/hook"

    test_response = client.post(f"/api/v1/projects/{project_id}/webhook/test")
    assert test_response.status_code == 202
    assert test_response.json() == {"status": "queued"}
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][2] == "webhook.test"
    assert dispatcher.calls[0][3] == "https://example.test/hook"
    assert dispatcher.calls[0][4] is None
    assert dispatcher.calls[0][5] is True

    _cleanup_overrides()


def test_project_webhook_non_owner_forbidden(tmp_path) -> None:
    owner = User(
        id="owner",
        email="owner@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    client, _ = _make_client(tmp_path, current_user=owner)
    project = client.post("/api/v1/projects", json={"name": "Owned"}).json()
    project_id = project["id"]

    app.dependency_overrides[get_current_user] = lambda: User(
        id="other",
        email="other@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )

    get_response = client.get(f"/api/v1/projects/{project_id}/webhook")
    put_response = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={"enabled": True, "url": "https://example.test/hook"},
    )
    assert get_response.status_code == 404
    assert put_response.status_code == 404
    _cleanup_overrides()


def test_project_webhook_validation_errors(tmp_path) -> None:
    client, _ = _make_client(tmp_path)
    project_id = client.post("/api/v1/projects", json={"name": "Validation"}).json()["id"]

    invalid_url = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={"enabled": True, "url": "not-a-url"},
    )
    missing_url = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={"enabled": True, "url": None},
    )
    assert invalid_url.status_code == 422
    assert missing_url.status_code == 422
    _cleanup_overrides()


def test_project_webhook_rejects_private_hosts(tmp_path) -> None:
    client, _ = _make_client(tmp_path)
    project_id = client.post("/api/v1/projects", json={"name": "Unsafe Host Validation"}).json()["id"]
    _set_protect_enabled(client, project_id)

    private_host = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={"enabled": True, "url": "https://127.0.0.1/hook"},
    )
    localhost_test = client.post(
        f"/api/v1/projects/{project_id}/webhook/test",
        json={"url": "https://localhost/hook"},
    )
    assert private_host.status_code == 422
    assert localhost_test.status_code == 422
    _cleanup_overrides()


def test_project_webhook_test_is_available_in_observe_mode(tmp_path) -> None:
    client, dispatcher = _make_client(tmp_path)
    project_id = client.post("/api/v1/projects", json={"name": "Webhook Test Override"}).json()["id"]

    put_response = client.put(
        f"/api/v1/projects/{project_id}/webhook",
        json={"enabled": False, "url": "https://saved.test/hook"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["enabled"] is False

    test_response = client.post(
        f"/api/v1/projects/{project_id}/webhook/test",
        json={
            "url": "https://draft.test/hook",
        },
    )
    assert test_response.status_code == 202
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][3] == "https://draft.test/hook"
    assert dispatcher.calls[0][4] is None

    _cleanup_overrides()


def test_project_webhook_last_status_ignores_webhook_tests(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/webhook_last_status_ignore_tests.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)
    service = ProjectService(project_repository=ProjectRepositoryImpl(session_factory=session_factory))
    dispatcher = FakeWebhookDispatcher()
    current_user = User(
        id="u1",
        email="u1@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[get_webhook_dispatcher] = lambda: dispatcher
    app.dependency_overrides[get_transport_outbox_repository] = lambda: TransportOutboxRepositoryImpl(session_factory=session_factory)
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)

    project_id = client.post("/api/v1/projects", json={"name": "Webhook Last Status"}).json()["id"]
    base_now = datetime(2026, 3, 17, 6, 45, tzinfo=timezone.utc)

    with session_factory.create_session() as session:
        session.add_all(
            [
                TransportOutboxRecord(
                    id="outbox-real-failure",
                    project_id=project_id,
                    kind="webhook",
                    event_type="incident.warn",
                    destination="https://example.test/hook",
                    subject=None,
                    template=None,
                    payload={"event": "incident.warn"},
                    dedupe_key="incident-warn-failure",
                    status="dead",
                    attempts=1,
                    max_attempts=1,
                    next_attempt_at=base_now,
                    last_error_code="webhook_http_error",
                    last_error_message="HTTP 500",
                    created_at=base_now,
                    updated_at=base_now,
                    sent_at=base_now,
                    delivered_at=None,
                ),
                TransportOutboxRecord(
                    id="outbox-test-success",
                    project_id=project_id,
                    kind="webhook",
                    event_type="webhook.test",
                    destination="https://example.test/hook",
                    subject=None,
                    template=None,
                    payload={"event": "webhook.test"},
                    dedupe_key="webhook-test-success",
                    status="delivered",
                    attempts=1,
                    max_attempts=1,
                    next_attempt_at=base_now + timedelta(minutes=1),
                    last_error_code=None,
                    last_error_message=None,
                    created_at=base_now + timedelta(minutes=1),
                    updated_at=base_now + timedelta(minutes=1),
                    sent_at=base_now + timedelta(minutes=1),
                    delivered_at=base_now + timedelta(minutes=1),
                ),
            ]
        )
        session.commit()

    response = client.get(f"/api/v1/projects/{project_id}/webhook")
    assert response.status_code == 200
    assert response.json()["last_status"] == "failed"
    assert response.json()["last_error"] == "HTTP 500"

    _cleanup_overrides()
