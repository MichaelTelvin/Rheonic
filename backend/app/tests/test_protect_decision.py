from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.metrics_service import MetricsService
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.project_service import ProjectService
from app.application.services.protect_service import ProtectService
from app.dependencies import (
    get_current_user,
    get_ingest_key_service,
    get_metrics_service,
    get_project_service,
    get_protect_action_store,
    get_protect_service,
)
from app.domain.models.event import Event
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.rolling_window import RollingWindow
from app.main import app


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.lists: dict[str, list[object]] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set_persistent(self, key: str, value: object) -> None:
        self.values[key] = value

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def incr(self, key: str) -> int:
        current = self.values.get(key, 0)
        next_value = int(current) + 1
        self.values[key] = next_value
        return next_value

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
        self.ttls[key] = ttl_seconds
        return True


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def add_recent(self, event: Event) -> None:
        self.events.append(event)

    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        return [event for event in self.events if event.project_id == project_id][-limit:]


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _make_client(tmp_path, *, cooldown_seconds: int = 60) -> tuple[TestClient, RollingWindow, FakeEventRepository]:
    db_url = f"sqlite:///{tmp_path}/protect_decision.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    redis_client = FakeRedisClient()
    rolling_window = RollingWindow(client=redis_client, now_ms_provider=lambda: 1_000_000_000_000)
    project_repository = ProjectRepositoryImpl(session_factory=session_factory)
    project_service = ProjectService(project_repository=project_repository)
    ingest_key_service = IngestKeyService(
        ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
        project_repository=project_repository,
    )
    event_repository = FakeEventRepository()
    protect_action_store = ProtectActionStore(redis_client=redis_client)  # type: ignore[arg-type]
    protect_service = ProtectService(
        ingest_key_service=ingest_key_service,
        event_repository=event_repository,  # type: ignore[arg-type]
        realtime_counters=rolling_window,
        protect_action_store=protect_action_store,
        protect_block_cooldown_seconds=cooldown_seconds,
    )
    metrics_service = MetricsService(
        realtime_counters=rolling_window,
        protect_action_store=protect_action_store,
        project_repository=project_repository,
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
    app.dependency_overrides[get_protect_action_store] = lambda: protect_action_store
    app.dependency_overrides[get_metrics_service] = lambda: metrics_service
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app), rolling_window, event_repository


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


def _decision(client: TestClient, ingest_key: str, body: dict[str, object] | None = None) -> dict[str, object]:
    response = client.post(
        "/api/v1/protect/decision",
        headers={"X-Project-Ingest-Key": ingest_key},
        json=body or {"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert response.status_code == 200
    return response.json()


def _event(project_id: str, provider: str, model: str, *, status: str, http_status: int, total_tokens: int, created_at: datetime) -> Event:
    return Event(
        id=f"evt-{project_id}-{provider}-{model}-{created_at.timestamp()}",
        ts=created_at,
        project_id=project_id,
        provider=provider,
        model=model,
        environment="dev",
        input_tokens=max(total_tokens // 2, 1),
        output_tokens=max(total_tokens // 2, 1),
        total_tokens=total_tokens,
        latency_ms=100,
        status=status,
        error_type="provider_error" if status == "error" else None,
        http_status=http_status,
        created_at=created_at,
    )


def test_protect_disabled_returns_allow_and_predictive_disabled(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Disabled")
    _set_protect(client, project_id, protect_enabled=False, protect_max_tok_per_min=100)
    decision = _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 90})
    assert decision["decision"] == "allow"
    assert decision["reason"] == "ok"
    assert decision["snapshot"]["predictive"]["enabled"] is False
    _cleanup_overrides()


def test_caps_breach_blocks_with_cap_reason(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Caps")
    _set_protect(client, project_id, protect_enabled=True, protect_max_req_per_min=2, protect_max_tok_per_min=1000)
    for _ in range(2):
        rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=10)
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "block"
    assert decision["reason"] == "req_cap_breach"
    _cleanup_overrides()


def test_near_cap_warns_when_predictive_reaches_warn_ratio(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 15},
    )
    assert decision["decision"] == "warn"
    assert decision["reason"] == "near_cap"
    _cleanup_overrides()


def test_retry_storm_warns_in_preflight(tmp_path) -> None:
    client, _, events = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Retry Storm")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=100000)

    now = datetime.now(timezone.utc)
    events.add_recent(_event(project_id, "openai", "gpt-4o-mini", status="error", http_status=500, total_tokens=50, created_at=now - timedelta(seconds=4)))
    events.add_recent(_event(project_id, "openai", "gpt-4o-mini", status="error", http_status=501, total_tokens=50, created_at=now - timedelta(seconds=3)))
    events.add_recent(_event(project_id, "openai", "gpt-4o-mini", status="error", http_status=502, total_tokens=50, created_at=now - timedelta(seconds=2)))
    events.add_recent(_event(project_id, "openai", "gpt-4o-mini", status="error", http_status=503, total_tokens=50, created_at=now - timedelta(seconds=1)))
    events.add_recent(_event(project_id, "openai", "gpt-4o-mini", status="error", http_status=504, total_tokens=50, created_at=now))

    decision = _decision(client, ingest_key)
    assert decision["decision"] == "warn"
    assert decision["reason"] == "retry_storm"
    _cleanup_overrides()


def test_protect_metrics_support_provider_filter_with_same_schema(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Metrics")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)

    _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})  # allow
    _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 180})  # warn

    _decision(client, ingest_key, body={"provider": "anthropic", "model": "claude-3-5-sonnet", "input_tokens_estimate": 180})  # warn

    all_metrics = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert all_metrics.status_code == 200
    payload = all_metrics.json()
    assert set(payload.keys()) == {
        "allowed_60m",
        "warned_60m",
        "blocked_60m",
        "decision_timeouts_60m",
        "last",
        "decision_latency_p50_60m_ms",
        "decision_latency_p95_60m_ms",
    }
    assert payload["allowed_60m"] >= 1
    assert payload["warned_60m"] >= 2

    openai_metrics = client.get(f"/api/v1/metrics/protect?project_id={project_id}&provider=openai")
    assert openai_metrics.status_code == 200
    assert openai_metrics.json()["warned_60m"] >= 1

    anthropic_metrics = client.get(f"/api/v1/metrics/protect?project_id={project_id}&provider=anthropic")
    assert anthropic_metrics.status_code == 200
    assert anthropic_metrics.json()["warned_60m"] >= 1
    _cleanup_overrides()
