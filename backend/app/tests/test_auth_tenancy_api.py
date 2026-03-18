# API tests for auth and tenant scoping.
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.dependencies import get_db_session_factory, get_redis_client, get_settings
from app.infrastructure.db.models import Base, IncidentRecord
from app.main import app


class _FakeRedisClient:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        value = self._values.get(key, 0) + 1
        self._values[key] = value
        return value

    def expire(self, key: str, ttl_seconds: int) -> bool:
        _ = (key, ttl_seconds)
        return True


def _make_client(tmp_path, *, redis_client: _FakeRedisClient | None = None) -> TestClient:
    # Configure isolated DB and JWT settings for auth tests.
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/auth_tenancy_test.db"
    os.environ["JWT_SECRET"] = "test-secret"
    os.environ["APP_ENV"] = "dev"
    os.environ["AUTH_RATE_LIMIT_WINDOW_SECONDS"] = "60"
    os.environ["AUTH_REGISTER_RATE_LIMIT_PER_WINDOW"] = "3"
    os.environ["AUTH_LOGIN_RATE_LIMIT_PER_WINDOW"] = "3"
    os.environ["AUTH_REFRESH_RATE_LIMIT_PER_WINDOW"] = "3"
    get_db_session_factory.cache_clear()
    get_settings.cache_clear()
    app.dependency_overrides.clear()
    resolved_redis_client = redis_client or _FakeRedisClient()
    app.dependency_overrides[get_redis_client] = lambda: resolved_redis_client
    session_factory = get_db_session_factory()
    Base.metadata.create_all(bind=session_factory.engine)
    return TestClient(app)


def _register_and_login(client: TestClient, email: str, password: str) -> None:
    # Register and login a user into the client's cookie jar.
    register_response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register_response.status_code == 200
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200


def test_register_and_login_happy_path_sets_auth_cookies(tmp_path) -> None:
    # Register/login should succeed, return user info, and set auth cookies.
    with _make_client(tmp_path) as client:
        register_response = client.post("/api/v1/auth/register", json={"email": "User@Example.com", "password": "password123"})
        assert register_response.status_code == 200
        assert register_response.json()["email"] == "user@example.com"
        assert "password_hash" not in register_response.json()

        login_response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "password123"})
        assert login_response.status_code == 200
        login_body = login_response.json()
        assert login_body["user"]["email"] == "user@example.com"
        assert "access_token" not in login_body
        assert "refresh_token" not in login_body
        settings = get_settings()
        assert login_response.cookies.get(settings.auth_access_cookie_name)
        assert login_response.cookies.get(settings.auth_refresh_cookie_name)


def test_refresh_issues_new_cookie_backed_session(tmp_path) -> None:
    # Refresh endpoint should exchange a valid refresh cookie for a new auth cookie pair.
    with _make_client(tmp_path) as client:
        _register_and_login(client, "refresh@example.com", "password123")
        refresh_response = client.post("/api/v1/auth/refresh")
        assert refresh_response.status_code == 200
        payload = refresh_response.json()
        assert payload["user"]["email"] == "refresh@example.com"
        settings = get_settings()
        assert refresh_response.cookies.get(settings.auth_access_cookie_name)
        assert refresh_response.cookies.get(settings.auth_refresh_cookie_name)


def test_refresh_rejects_invalid_cookie(tmp_path) -> None:
    # Refresh endpoint should reject invalid refresh cookie values.
    with _make_client(tmp_path) as client:
        settings = get_settings()
        client.cookies.set(
            settings.auth_refresh_cookie_name,
            "not-a-token",
            path=f"{settings.api_prefix}/v1/auth",
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == 401


def test_me_and_logout_use_cookie_session(tmp_path) -> None:
    # Browser session endpoints should resolve the current user and clear cookies on logout.
    with _make_client(tmp_path) as client:
        _register_and_login(client, "session@example.com", "password123")

        me_response = client.get("/api/v1/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "session@example.com"

        logout_response = client.post("/api/v1/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.json() == {"status": "ok"}

        post_logout_me = client.get("/api/v1/auth/me")
        assert post_logout_me.status_code == 401


def test_protected_routes_require_cookie(tmp_path) -> None:
    # Protected routes must reject missing auth cookies.
    with _make_client(tmp_path) as client:
        response = client.get("/api/v1/projects")
        assert response.status_code == 401
        assert response.json() == {"error": {"code": "unauthorized", "message": "not authenticated"}}


def test_protected_routes_with_cookie_return_200(tmp_path) -> None:
    # Protected routes should work with valid auth cookies.
    with _make_client(tmp_path) as client:
        _register_and_login(client, "owner@example.com", "password123")
        response = client.get("/api/v1/projects")
        assert response.status_code == 200


def test_tenant_scoping_blocks_cross_user_project_access(tmp_path) -> None:
    # User B should not access User A project keys from a separate cookie session.
    with _make_client(tmp_path) as owner_client, _make_client(tmp_path) as other_client:
        _register_and_login(owner_client, "owner@example.com", "password123")
        create_project = owner_client.post("/api/v1/projects", json={"name": "Owner Project"})
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        _register_and_login(other_client, "other@example.com", "password123")
        other_list = other_client.get(f"/api/v1/projects/{project_id}/keys")
        assert other_list.status_code == 404


def test_tenant_scoping_blocks_cross_user_key_revoke(tmp_path) -> None:
    # User B must not revoke User A key from a separate cookie session.
    with _make_client(tmp_path) as owner_client, _make_client(tmp_path) as other_client:
        _register_and_login(owner_client, "owner_revoke@example.com", "password123")
        create_project = owner_client.post("/api/v1/projects", json={"name": "Owner Revoke Project"})
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]
        create_key = owner_client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "prod"})
        assert create_key.status_code == 200
        key_id = create_key.json()["key_id"]

        _register_and_login(other_client, "other_revoke@example.com", "password123")
        revoke_response = other_client.post(f"/api/v1/keys/{key_id}/revoke")
        assert revoke_response.status_code == 404


def test_tenant_scoping_blocks_cross_user_incident_resolve(tmp_path) -> None:
    # User B must not resolve User A incident from a separate cookie session.
    with _make_client(tmp_path) as owner_client, _make_client(tmp_path) as other_client:
        _register_and_login(owner_client, "owner_inc@example.com", "password123")
        create_project = owner_client.post("/api/v1/projects", json={"name": "Owner Incident Project"})
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

        _register_and_login(other_client, "other_inc@example.com", "password123")
        resolve_response = other_client.post(f"/api/v1/incidents/{incident_id}/resolve")
        assert resolve_response.status_code == 404


def test_tenant_scoping_blocks_cross_user_metrics_read(tmp_path) -> None:
    # User B must not read realtime metrics for User A project from a separate cookie session.
    with _make_client(tmp_path) as owner_client, _make_client(tmp_path) as other_client:
        _register_and_login(owner_client, "owner_metrics@example.com", "password123")
        create_project = owner_client.post("/api/v1/projects", json={"name": "Owner Metrics Project"})
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        _register_and_login(other_client, "other_metrics@example.com", "password123")
        metrics_response = other_client.get(f"/api/v1/metrics/realtime?project_id={project_id}")
        assert metrics_response.status_code == 404


def test_project_providers_endpoint_auth_and_tenant_scoping(tmp_path) -> None:
    # Providers endpoint should require auth and enforce ownership.
    with _make_client(tmp_path) as owner_client, _make_client(tmp_path) as other_client:
        _register_and_login(owner_client, "owner_providers@example.com", "password123")
        create_project = owner_client.post("/api/v1/projects", json={"name": "Owner Providers Project"})
        assert create_project.status_code == 200
        project_id = create_project.json()["id"]

        unauthenticated = other_client.get(f"/api/v1/projects/{project_id}/providers")
        assert unauthenticated.status_code == 401

        _register_and_login(other_client, "other_providers@example.com", "password123")
        forbidden = other_client.get(f"/api/v1/projects/{project_id}/providers")
        assert forbidden.status_code == 404


def test_sanitization_rejects_invalid_email_project_and_key_label(tmp_path) -> None:
    # Invalid email/project/key inputs should fail with 400 and clear messages.
    with _make_client(tmp_path) as client:
        bad_email = client.post("/api/v1/auth/register", json={"email": "bad\n@email.com", "password": "password123"})
        assert bad_email.status_code == 400
        assert bad_email.json()["error"]["message"] == "email contains invalid characters"

        _register_and_login(client, "valid@example.com", "password123")
        bad_project = client.post("/api/v1/projects", json={"name": "Bad/Project"})
        assert bad_project.status_code == 400
        assert bad_project.json()["error"]["message"] == "project name has invalid format"

        good_project = client.post("/api/v1/projects", json={"name": "Project One"})
        assert good_project.status_code == 200
        project_id = good_project.json()["id"]

        bad_key = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "bad\tlabel"})
        assert bad_key.status_code == 400
        assert bad_key.json()["error"]["message"] == "key label contains invalid characters"


def test_register_is_rate_limited_per_client_and_email(tmp_path) -> None:
    with _make_client(tmp_path, redis_client=_FakeRedisClient()) as client:
        for index in range(3):
            response = client.post("/api/v1/auth/register", json={"email": f"user{index}@example.com", "password": "password123"})
            assert response.status_code == 200

        limited = client.post("/api/v1/auth/register", json={"email": "overflow@example.com", "password": "password123"})
        assert limited.status_code == 429
        assert limited.json() == {"error": {"code": "too_many_requests", "message": "rate limit exceeded"}}


def test_login_is_rate_limited_after_repeated_failures(tmp_path) -> None:
    with _make_client(tmp_path, redis_client=_FakeRedisClient()) as client:
        register_response = client.post("/api/v1/auth/register", json={"email": "user@example.com", "password": "password123"})
        assert register_response.status_code == 200

        for _ in range(3):
            response = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong-password"})
            assert response.status_code == 401

        limited = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "password123"})
        assert limited.status_code == 429
        assert limited.json() == {"error": {"code": "too_many_requests", "message": "rate limit exceeded"}}


def test_refresh_is_rate_limited_by_client(tmp_path) -> None:
    with _make_client(tmp_path, redis_client=_FakeRedisClient()) as client:
        for _ in range(3):
            response = client.post("/api/v1/auth/refresh")
            assert response.status_code == 401

        limited = client.post("/api/v1/auth/refresh")
        assert limited.status_code == 429
        assert limited.json() == {"error": {"code": "too_many_requests", "message": "rate limit exceeded"}}
