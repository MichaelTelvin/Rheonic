# API tests for protect preflight decision endpoint.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.application.services.protect_service import ProtectService
from app.dependencies import (
    get_current_user,
    get_ingest_key_service,
    get_project_service,
    get_protect_service,
)
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.infrastructure.redis.rolling_window import RollingWindow
from app.main import app


class FakeRedisClient:
    # In-memory fake redis adapter for rolling counters + severity cache.

    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.lists: dict[str, list[object]] = {}

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set_persistent(self, key: str, value: object) -> None:
        self.values[key] = value

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        _ = ex
        self.values[key] = value
        return True

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        zset = self.zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = score
        return added

    def zremrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> int:
        zset = self.zsets.get(key, {})
        to_delete = [member for member, score in zset.items() if float(min_score) <= score <= float(max_score)]
        for member in to_delete:
            del zset[member]
        return len(to_delete)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        zset = self.zsets.get(key, {})
        max_bound = float("inf") if max_score == float("inf") else float(max_score)
        selected = [(member, score) for member, score in zset.items() if float(min_score) <= score <= max_bound]
        selected.sort(key=lambda item: (item[1], item[0]))
        return [member.encode("utf-8") for member, _ in selected]

    def lpush(self, key: str, value: object) -> int:
        values = self.lists.setdefault(key, [])
        values.insert(0, value)
        return len(values)

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        values = self.lists.setdefault(key, [])
        values[:] = values[start : stop + 1]
        return True

    def lrange(self, key: str, start: int, stop: int) -> list[object]:
        values = self.lists.get(key, [])
        return values[start : stop + 1]

    def expire(self, key: str, ttl_seconds: int) -> bool:
        _ = key
        _ = ttl_seconds
        return True


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


def _make_client(tmp_path) -> tuple[TestClient, RollingWindow, IncidentSeverityCache]:
    db_url = f"sqlite:///{tmp_path}/protect_decision.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    redis_client = FakeRedisClient()
    rolling_window = RollingWindow(client=redis_client, now_ms_provider=lambda: 1_000_000_000_000)
    incident_severity_cache = IncidentSeverityCache(redis_client=redis_client)  # type: ignore[arg-type]
    project_repository = ProjectRepositoryImpl(session_factory=session_factory)
    project_service = ProjectService(project_repository=project_repository)
    ingest_key_service = IngestKeyService(
        ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
        project_repository=project_repository,
    )
    protect_service = ProtectService(
        ingest_key_service=ingest_key_service,
        realtime_counters=rolling_window,
        incident_severity_cache=incident_severity_cache,
    )
    current_user = User(
        id="u-protect",
        email="protect@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )

    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_ingest_key_service] = lambda: ingest_key_service
    app.dependency_overrides[get_protect_service] = lambda: protect_service
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app), rolling_window, incident_severity_cache


def _create_project_and_key(client: TestClient, project_name: str) -> tuple[str, str]:
    project_response = client.post("/api/v1/projects", json={"name": project_name})
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "dev"})
    assert key_response.status_code == 200
    plaintext_key = key_response.json()["key"]
    return project_id, plaintext_key


def _set_protect(
    client: TestClient,
    project_id: str,
    *,
    protect_enabled: bool,
    protect_fail_mode: str = "open",
    protect_max_req_per_min: int | None = None,
    protect_max_tok_per_min: int | None = None,
    protect_decision_timeout_ms: int = 100,
) -> None:
    response = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": protect_enabled,
            "protect_fail_mode": protect_fail_mode,
            "protect_max_req_per_min": protect_max_req_per_min,
            "protect_max_tok_per_min": protect_max_tok_per_min,
            "protect_decision_timeout_ms": protect_decision_timeout_ms,
        },
    )
    assert response.status_code == 200


def _decision(client: TestClient, ingest_key: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/protect/decision",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert response.status_code == 200
    return response.json()


def test_protect_disabled_returns_allow(tmp_path) -> None:
    client, _, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Disabled")
    _set_protect(client, project_id, protect_enabled=False)
    severity_cache.set(project_id, "high")
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "allow"
    assert decision["reason"] == "ok"
    _cleanup_overrides()


def test_req_limit_exceeded_blocks(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Req Limit")
    _set_protect(client, project_id, protect_enabled=True, protect_max_req_per_min=3)
    for _ in range(3):
        rolling_window.increment_project_60s(project_id=project_id, total_tokens=10)
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "block"
    assert decision["reason"] == "req_limit"
    _cleanup_overrides()


def test_tok_limit_exceeded_blocks(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Tok Limit")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=100)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=150)
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "block"
    assert decision["reason"] == "tok_limit"
    _cleanup_overrides()


def test_medium_incident_returns_warn(tmp_path) -> None:
    client, _, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Medium Incident")
    _set_protect(client, project_id, protect_enabled=True)
    severity_cache.set(project_id, "medium")
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "warn"
    assert decision["reason"] == "incident_medium"
    _cleanup_overrides()


def test_high_incident_returns_block(tmp_path) -> None:
    client, _, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect High Incident")
    _set_protect(client, project_id, protect_enabled=True)
    severity_cache.set(project_id, "high")
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "block"
    assert decision["reason"] == "incident_high"
    _cleanup_overrides()


def test_disabled_with_high_incident_still_allows(tmp_path) -> None:
    client, _, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Disabled High Incident")
    _set_protect(client, project_id, protect_enabled=False)
    severity_cache.set(project_id, "high")
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "allow"
    assert decision["reason"] == "ok"
    _cleanup_overrides()


def test_decision_snapshot_includes_counters_and_thresholds(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Snapshot")
    _set_protect(
        client,
        project_id,
        protect_enabled=True,
        protect_max_req_per_min=10,
        protect_max_tok_per_min=500,
        protect_decision_timeout_ms=250,
    )
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=120)
    decision = _decision(client, ingest_key)
    snapshot = decision["snapshot"]
    assert snapshot["requests_60s"] == 1
    assert snapshot["tokens_60s"] == 120
    assert snapshot["protect_max_req_per_min"] == 10
    assert snapshot["protect_max_tok_per_min"] == 500
    assert decision["protect_decision_timeout_ms"] == 250
    _cleanup_overrides()


def test_invalid_ingest_key_returns_401(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    response = client.post(
        "/api/v1/protect/decision",
        headers={"X-Project-Ingest-Key": "invalid"},
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "invalid ingest key"
    _cleanup_overrides()
