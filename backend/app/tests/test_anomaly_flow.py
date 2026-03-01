from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.dependencies import get_db_session_factory
from app.infrastructure.db.models import Base
from app.main import app


def _make_client() -> TestClient:
    session_factory = get_db_session_factory()
    Base.metadata.create_all(bind=session_factory.engine)
    return TestClient(app)


def _event_payload(total_tokens: int, provider: str, model: str, env: str = "dev") -> dict[str, object]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "model": model,
        "environment": env,
        "response": {"total_tokens": total_tokens},
        "status": "error",
        "http_status": 502,
        "error_type": "provider_error",
    }


def _auth_headers(client: TestClient) -> dict[str, str]:
    email = f"anomaly-{datetime.now(timezone.utc).timestamp()}@example.com"
    password = "Password123!"
    register_response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert register_response.status_code == 200
    login_response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project_and_key(client: TestClient, name: str, headers: dict[str, str]) -> tuple[str, str]:
    project_response = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "dev"}, headers=headers)
    assert key_response.status_code == 200
    return project_id, key_response.json()["key"]


def test_incidents_provider_filter_returns_scoped_rows() -> None:
    client = _make_client()
    headers = _auth_headers(client)
    project_id, ingest_key = _create_project_and_key(client, "provider filter", headers)

    # Configure protect for deterministic warn-capable flow and send retry failures.
    set_protect = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "protect_max_req_per_min": 1000,
            "protect_max_tok_per_min": 100000,
            "protect_decision_timeout_ms": 100,
        },
        headers=headers,
    )
    assert set_protect.status_code == 200

    for _ in range(6):
        r = client.post(
            "/api/v1/events",
            json=_event_payload(50, provider="openai", model="gpt-4o-mini"),
            headers={"X-Project-Ingest-Key": ingest_key},
        )
        assert r.status_code == 202

    for _ in range(6):
        r = client.post(
            "/api/v1/events",
            json=_event_payload(60, provider="anthropic", model="claude-3-5-sonnet"),
            headers={"X-Project-Ingest-Key": ingest_key},
        )
        assert r.status_code == 202

    all_rows = client.get(f"/api/v1/incidents?project_id={project_id}&status=open", headers=headers)
    assert all_rows.status_code == 200
    assert len(all_rows.json()) >= 2

    openai_rows = client.get(f"/api/v1/incidents?project_id={project_id}&status=open&provider=openai", headers=headers)
    assert openai_rows.status_code == 200
    assert openai_rows.json()
    assert all(row["evidence"].get("provider") == "openai" for row in openai_rows.json())

    anthropic_rows = client.get(
        f"/api/v1/incidents?project_id={project_id}&status=open&provider=anthropic",
        headers=headers,
    )
    assert anthropic_rows.status_code == 200
    assert anthropic_rows.json()
    assert all(row["evidence"].get("provider") == "anthropic" for row in anthropic_rows.json())


def test_incident_dedup_updates_existing_row_count() -> None:
    client = _make_client()
    headers = _auth_headers(client)
    project_id, ingest_key = _create_project_and_key(client, "dedup updates", headers)

    set_protect = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "protect_max_req_per_min": 1000,
            "protect_max_tok_per_min": 100000,
            "protect_decision_timeout_ms": 100,
        },
        headers=headers,
    )
    assert set_protect.status_code == 200

    for _ in range(6):
        r = client.post(
            "/api/v1/events",
            json=_event_payload(75, provider="openai", model="gpt-4o-mini"),
            headers={"X-Project-Ingest-Key": ingest_key},
        )
        assert r.status_code == 202

    rows = client.get(f"/api/v1/incidents?project_id={project_id}&status=open&provider=openai", headers=headers)
    assert rows.status_code == 200
    assert len(rows.json()) >= 1
    retry_rows = [row for row in rows.json() if row["type"] == "retry_storm"]
    assert retry_rows
    assert int(retry_rows[0]["evidence"].get("count", 0)) >= 1


def test_retry_storm_ingest_returns_202_and_incident_is_listed() -> None:
    client = _make_client()
    headers = _auth_headers(client)
    project_id, ingest_key = _create_project_and_key(client, "retry storm ingest", headers)

    set_protect = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": True,
            "protect_fail_mode": "open",
            "protect_max_req_per_min": 1000,
            "protect_max_tok_per_min": 100000,
            "protect_decision_timeout_ms": 100,
        },
        headers=headers,
    )
    assert set_protect.status_code == 200

    for _ in range(6):
        response = client.post(
            "/api/v1/events",
            json=_event_payload(55, provider="openai", model="gpt-4o-mini"),
            headers={"X-Project-Ingest-Key": ingest_key},
        )
        assert response.status_code == 202

    rows = client.get(f"/api/v1/incidents?project_id={project_id}&status=open&provider=openai", headers=headers)
    assert rows.status_code == 200
    retry_rows = [row for row in rows.json() if row["type"] == "retry_storm"]
    assert retry_rows
