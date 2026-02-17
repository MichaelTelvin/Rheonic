# API tests for auth and tenant scoping.
import os

from fastapi.testclient import TestClient

from app.dependencies import get_db_session_factory, get_settings
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
        assert len(login_body["access_token"]) > 20
        assert login_body["user"]["email"] == "user@example.com"


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
