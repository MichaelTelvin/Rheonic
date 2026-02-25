# API tests for auth and tenant scoping.
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.dependencies import get_db_session_factory, get_settings
from app.infrastructure.db.models import IncidentRecord
from app.main import app


def _make_client(tmp_path) -> TestClient:
    # Configure isolated DB and JWT settings for auth tests.
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/auth_tenancy_test.db"
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["APP_ENV"] = "dev"
    get_db_session_factory.cache_clear()
    get_settings.cache_clear()
    return TestClient(app)


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    # Register and login a user, returning bearer headers.
    register_response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register_response.status_code == 200
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_and_login_happy_path_returns_jwt(tmp_path) -> None:
    # Register/login should succeed and return an access token payload.
    with _make_client(tmp_path) as client:
        register_response = client.post("/api/v1/auth/register", json={"email": "User@Example.com", "password": "password123"})
        assert register_response.status_code == 200
        assert register_response.json()["email"] == "user@example.com"
        assert "password_hash" not in register_response.json()

        login_response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "password123"})
        assert login_response.status_code == 200
        login_body = login_response.json()
        assert login_body["token_type"] == "bearer"
        assert isinstance(login_body["access_token"], str)
        assert isinstance(login_body["refresh_token"], str)
        assert len(login_body["access_token"]) > 20
        assert len(login_body["refresh_token"]) > 20
        assert login_body["user"]["email"] == "user@example.com"


def test_refresh_issues_new_tokens(tmp_path) -> None:
    # Refresh endpoint should exchange a valid refresh token for a new auth pair.
    with _make_client(tmp_path) as client:
        client.post("/api/v1/auth/register", json={"email": "refresh@example.com", "password": "password123"})
        login_response = client.post("/api/v1/auth/login", json={"email": "refresh@example.com", "password": "password123"})
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]

        refresh_response = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_response.status_code == 200
        payload = refresh_response.json()
        assert payload["token_type"] == "bearer"
        assert isinstance(payload["access_token"], str)
        assert isinstance(payload["refresh_token"], str)
        assert payload["user"]["email"] == "refresh@example.com"


def test_refresh_rejects_invalid_token(tmp_path) -> None:
    # Refresh endpoint should reject invalid refresh token payloads.
    with _make_client(tmp_path) as client:
        response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-token"})
        assert response.status_code == 401


def test_protected_routes_require_token(tmp_path) -> None:
    # Protected routes must reject missing bearer token.
    with _make_client(tmp_path) as client:
        response = client.get("/api/v1/projects")
        assert response.status_code == 401
        assert response.json() == {"error": {"code": "unauthorized", "message": "not authenticated"}}


def test_protected_routes_with_token_return_200(tmp_path) -> None:
    # Protected routes should work with valid bearer token.
    with _make_client(tmp_path) as client:
        headers = _auth_headers(client, "owner@example.com", "password123")
        response = client.get("/api/v1/projects", headers=headers)
        assert response.status_code == 200


def test_tenant_scoping_blocks_cross_user_project_access(tmp_path) -> None:
    # User B should not access User A project keys.
    with _make_client(tmp_path) as client:
        owner_headers = _auth_headers(client, "owner@example.com", "password123")
        create_project = client.post("/api/v1/projects", json={"name": "Owner Project"}, headers=owner_headers)
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        other_headers = _auth_headers(client, "other@example.com", "password123")
        other_list = client.get(f"/api/v1/projects/{project_id}/keys", headers=other_headers)
        assert other_list.status_code == 404


def test_tenant_scoping_blocks_cross_user_key_revoke(tmp_path) -> None:
    # User B must not revoke User A key.
    with _make_client(tmp_path) as client:
        owner_headers = _auth_headers(client, "owner_revoke@example.com", "password123")
        create_project = client.post("/api/v1/projects", json={"name": "Owner Revoke Project"}, headers=owner_headers)
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]
        create_key = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "prod"}, headers=owner_headers)
        assert create_key.status_code == 200
        key_id = create_key.json()["key_id"]

        other_headers = _auth_headers(client, "other_revoke@example.com", "password123")
        revoke_response = client.post(f"/api/v1/keys/{key_id}/revoke", headers=other_headers)
        assert revoke_response.status_code == 404


def test_tenant_scoping_blocks_cross_user_incident_resolve(tmp_path) -> None:
    # User B must not resolve User A incident.
    with _make_client(tmp_path) as client:
        owner_headers = _auth_headers(client, "owner_inc@example.com", "password123")
        create_project = client.post("/api/v1/projects", json={"name": "Owner Incident Project"}, headers=owner_headers)
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        incident_id = str(uuid4())
        now = datetime.now(timezone.utc)
        session_factory = get_db_session_factory()
        with session_factory.create_session() as session:
            session.add(
                IncidentRecord(
                    id=incident_id,
                    project_id=project_id,
                    provider="openai",
                    type="retry_storm",
                    status="open",
                    evidence={"count": 1},
                    created_at=now,
                    resolved_at=None,
                    fingerprint=None,
                    last_seen_at=now,
                )
            )
            session.commit()

        other_headers = _auth_headers(client, "other_inc@example.com", "password123")
        resolve_response = client.post(f"/api/v1/incidents/{incident_id}/resolve", headers=other_headers)
        assert resolve_response.status_code == 404


def test_tenant_scoping_blocks_cross_user_metrics_read(tmp_path) -> None:
    # User B must not read realtime metrics for User A project.
    with _make_client(tmp_path) as client:
        owner_headers = _auth_headers(client, "owner_metrics@example.com", "password123")
        create_project = client.post("/api/v1/projects", json={"name": "Owner Metrics Project"}, headers=owner_headers)
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        other_headers = _auth_headers(client, "other_metrics@example.com", "password123")
        metrics_response = client.get(f"/api/v1/metrics/realtime?project_id={project_id}", headers=other_headers)
        assert metrics_response.status_code == 404


def test_project_providers_endpoint_auth_and_tenant_scoping(tmp_path) -> None:
    # Providers endpoint should require auth and enforce ownership.
    with _make_client(tmp_path) as client:
        owner_headers = _auth_headers(client, "owner_providers@example.com", "password123")
        create_project = client.post("/api/v1/projects", json={"name": "Owner Providers Project"}, headers=owner_headers)
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        unauthenticated = client.get(f"/api/v1/projects/{project_id}/providers")
        assert unauthenticated.status_code == 401

        other_headers = _auth_headers(client, "other_providers@example.com", "password123")
        forbidden = client.get(f"/api/v1/projects/{project_id}/providers", headers=other_headers)
        assert forbidden.status_code == 404


def test_sanitization_rejects_invalid_email_project_and_key_label(tmp_path) -> None:
    # Invalid email/project/key inputs should fail with 400 and clear messages.
    with _make_client(tmp_path) as client:
        bad_email = client.post("/api/v1/auth/register", json={"email": "bad\n@email.com", "password": "password123"})
        assert bad_email.status_code == 400
        assert bad_email.json()["error"]["message"] == "email contains invalid characters"

        headers = _auth_headers(client, "valid@example.com", "password123")
        bad_project = client.post("/api/v1/projects", json={"name": "Bad/Project"}, headers=headers)
        assert bad_project.status_code == 400
        assert bad_project.json()["error"]["message"] == "project name has invalid format"

        good_project = client.post("/api/v1/projects", json={"name": "Project One"}, headers=headers)
        assert good_project.status_code == 200
        project_id = good_project.json()["id"]

        bad_key = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "bad\tlabel"}, headers=headers)
        assert bad_key.status_code == 400
        assert bad_key.json()["error"]["message"] == "key label contains invalid characters"
