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

    def set_nx_ex(self, key: str, value: object, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ttl_seconds
        return True

    def incr(self, key: str) -> int:
        current = self.values.get(key, 0)
        next_value = int(current) + 1
        self.values[key] = next_value
        return next_value

    def incrby(self, key: str, amount: int) -> int:
        current = self.values.get(key, 0)
        next_value = int(current) + int(amount)
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

    def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return 1 if existed else 0


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.list_recent_calls = 0

    def add_recent(self, event: Event) -> None:
        self.events.append(event)

    def list_recent(self, project_id: str, limit: int = 100, provider: str | None = None) -> list[Event]:
        self.list_recent_calls += 1
        rows = [event for event in self.events if event.project_id == project_id]
        if provider:
            rows = [event for event in rows if event.provider == provider]
        return rows[-limit:]


class FakeWebhookDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def enqueue(
        self,
        project_id: str,
        payload: dict[str, object],
        event_type: str,
        *,
        override_url: str | None = None,
        force_send: bool = False,
    ) -> None:
        _ = (override_url, force_send)
        self.calls.append((project_id, event_type, payload))


class FakeTransportService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return "outbox-1"


def _cleanup_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _make_client(
    tmp_path,
    *,
    cooldown_seconds: int = 60,
    webhook_dispatcher: FakeWebhookDispatcher | None = None,
    transport_service: FakeTransportService | None = None,
    event_repository: FakeEventRepository | None = None,
) -> tuple[TestClient, RollingWindow, FakeEventRepository]:
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
    event_repository = event_repository or FakeEventRepository()
    protect_action_store = ProtectActionStore(redis_client=redis_client)  # type: ignore[arg-type]
    protect_service = ProtectService(
        ingest_key_service=ingest_key_service,
        event_repository=event_repository,  # type: ignore[arg-type]
        realtime_counters=rolling_window,
        protect_action_store=protect_action_store,
        protect_block_cooldown_seconds=cooldown_seconds,
        webhook_dispatcher=webhook_dispatcher,  # type: ignore[arg-type]
        transport_service=transport_service,  # type: ignore[arg-type]
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
    apply_clamp: bool = False,
    protect_fail_mode: str = "open",
    protect_max_req_per_min: int | None = None,
    protect_max_tok_per_min: int | None = None,
) -> None:
    response = client.put(
        f"/api/v1/projects/{project_id}/protect",
        json={
            "protect_enabled": protect_enabled,
            "protect_fail_mode": protect_fail_mode,
            "apply_clamp": apply_clamp,
            "protect_max_req_per_min": protect_max_req_per_min,
            "protect_max_tok_per_min": protect_max_tok_per_min,
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


def _event(
    project_id: str,
    provider: str,
    model: str,
    *,
    status: str,
    http_status: int,
    total_tokens: int,
    created_at: datetime,
    request_endpoint: str | None = "/chat/completions",
    request_feature: str = "manual-protect-demo",
) -> Event:
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
        request_endpoint=request_endpoint,
        request_feature=request_feature,
    )


def _protect_metrics(client: TestClient, project_id: str, provider: str = "openai") -> dict[str, object]:
    response = client.get(f"/api/v1/metrics/protect?project_id={project_id}&provider={provider}")
    assert response.status_code == 200
    return response.json()


def _incidents(client: TestClient, project_id: str, provider: str = "openai", status: str = "open") -> list[dict[str, object]]:
    response = client.get(f"/api/v1/incidents?project_id={project_id}&status={status}&provider={provider}")
    assert response.status_code == 200
    return response.json()


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


def test_caps_breach_enqueues_protection_block_email(tmp_path) -> None:
    transport = FakeTransportService()
    client, rolling_window, _ = _make_client(tmp_path, transport_service=transport)
    project_id, ingest_key = _create_project_and_key(client, "Protect Caps Email")
    _set_protect(client, project_id, protect_enabled=True, protect_max_req_per_min=2, protect_max_tok_per_min=1000)
    for _ in range(2):
        rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=10)
    decision = _decision(client, ingest_key)
    assert decision["decision"] == "block"
    assert len(transport.calls) == 1
    assert transport.calls[0]["event_type"] == "protection.block"
    assert transport.calls[0]["template"] == "protection_block"
    _cleanup_overrides()


def test_near_cap_warns_when_predictive_reaches_warn_ratio(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_tokens_estimate": 15,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    assert decision["reason"] == "near_cap"
    assert decision["apply_clamp_enabled"] is False
    assert isinstance(decision["clamp"], dict)
    assert int(decision["clamp"]["recommended_max_output_tokens"]) > 0
    assert decision["clamp"]["applied"] is False
    _cleanup_overrides()


def test_near_cap_warn_short_circuits_recent_event_lookup(tmp_path) -> None:
    event_repository = FakeEventRepository()
    client, rolling_window, _ = _make_client(tmp_path, event_repository=event_repository)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Fast Path")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_tokens_estimate": 15,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    assert decision["reason"] == "near_cap"
    assert event_repository.list_recent_calls == 0
    _cleanup_overrides()


def test_near_cap_warn_includes_apply_clamp_flag_when_enabled(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Clamp")
    _set_protect(client, project_id, protect_enabled=True, apply_clamp=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 10, "max_output_tokens": 64},
    )
    assert decision["decision"] == "warn"
    assert decision["reason"] == "near_cap"
    assert decision["apply_clamp_enabled"] is True
    assert decision["clamp"]["applied"] is False
    assert int(decision["clamp"]["recommended_max_output_tokens"]) <= 64
    metrics = _protect_metrics(client, project_id)
    assert metrics["warned_60m"] == 1
    assert metrics["last"] == {
        "decision": "warn",
        "reason": "near_cap",
        "source": "live",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_near_cap_warn_dispatches_protection_warn_webhook(tmp_path) -> None:
    dispatcher = FakeWebhookDispatcher()
    client, rolling_window, _ = _make_client(tmp_path, webhook_dispatcher=dispatcher)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Webhook")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "input_tokens_estimate": 10,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    warn_calls = [call for call in dispatcher.calls if call[1] == "protection.warn"]
    assert len(warn_calls) == 1
    _, _, payload = warn_calls[0]
    assert payload["event"] == "protection.warn"
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["environment"] == "dev"
    assert payload["reason"] == "near_cap"
    assert payload["apply_clamp_enabled"] is False
    assert isinstance(payload["clamp"], dict)
    _cleanup_overrides()


def test_near_cap_warn_dispatches_clamp_started_when_clamp_enabled(tmp_path) -> None:
    dispatcher = FakeWebhookDispatcher()
    client, rolling_window, _ = _make_client(tmp_path, webhook_dispatcher=dispatcher)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Clamp Webhook")
    _set_protect(client, project_id, protect_enabled=True, apply_clamp=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "input_tokens_estimate": 10,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    event_types = [event_type for _, event_type, _ in dispatcher.calls]
    assert "protection.warn" in event_types
    assert "protection.clamp_started" in event_types
    _cleanup_overrides()


def test_near_cap_warn_with_clamp_enabled_skips_warn_email_and_keeps_clamp_email(tmp_path) -> None:
    dispatcher = FakeWebhookDispatcher()
    transport = FakeTransportService()
    client, rolling_window, _ = _make_client(tmp_path, webhook_dispatcher=dispatcher, transport_service=transport)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Clamp Email")
    _set_protect(client, project_id, protect_enabled=True, apply_clamp=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "input_tokens_estimate": 10,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    event_types = [event_type for _, event_type, _ in dispatcher.calls]
    assert "protection.warn" in event_types
    assert "protection.clamp_started" in event_types
    assert [call["event_type"] for call in transport.calls] == ["protection.clamp_started"]
    assert [call["template"] for call in transport.calls] == ["protection_clamp_started"]
    _cleanup_overrides()


def test_near_cap_warn_creates_visible_incident_from_preflight(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Near Cap Incident")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=150)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "input_tokens_estimate": 10,
            "max_output_tokens": 64,
        },
    )
    assert decision["decision"] == "warn"
    incidents = _incidents(client, project_id, provider="openai")
    assert len(incidents) == 1
    assert incidents[0]["type"] == "near_cap"
    assert incidents[0]["evidence"]["near_cap_type"] == "tok"
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


def test_loop_suspect_warns_in_preflight_when_feature_matches(tmp_path) -> None:
    client, _, events = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Loop Suspect")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=100000)

    now = datetime.now(timezone.utc)
    for offset in range(7):
        events.add_recent(
            _event(
                project_id,
                "openai",
                "gpt-4o-mini",
                status="ok",
                http_status=200,
                total_tokens=60,
                created_at=now - timedelta(seconds=6 - offset),
                request_feature="manual-protect-demo",
            )
        )

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "dev",
            "feature": "manual-protect-demo",
        },
    )
    assert decision["decision"] == "warn"
    assert decision["reason"] == "loop_suspect"
    _cleanup_overrides()


def test_protect_decision_records_allow_warn_block_outcomes(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)

    allow_project_id, allow_ingest_key = _create_project_and_key(client, "Protect Outcome Allow")
    _set_protect(client, allow_project_id, protect_enabled=True, protect_max_req_per_min=1000, protect_max_tok_per_min=1000)
    allow_before = int(_protect_metrics(client, allow_project_id)["allowed_60m"])
    _decision(client, allow_ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    allow_metrics = _protect_metrics(client, allow_project_id)
    allow_after = int(allow_metrics["allowed_60m"])
    assert allow_after == allow_before + 1
    assert allow_metrics["last"] == {
        "decision": "allow",
        "reason": "ok",
        "source": "live",
        "ts": allow_metrics["last"]["ts"],
    }

    warn_project_id, warn_ingest_key = _create_project_and_key(client, "Protect Outcome Warn")
    _set_protect(client, warn_project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(warn_project_id, "openai"), total_tokens=170)
    warn_before = int(_protect_metrics(client, warn_project_id)["warned_60m"])
    _decision(
        client,
        warn_ingest_key,
        body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 20},
    )
    warn_metrics = _protect_metrics(client, warn_project_id)
    warn_after = int(warn_metrics["warned_60m"])
    assert warn_after == warn_before + 1
    assert warn_metrics["last"] == {
        "decision": "warn",
        "reason": "near_cap",
        "source": "live",
        "ts": warn_metrics["last"]["ts"],
    }

    block_project_id, block_ingest_key = _create_project_and_key(client, "Protect Outcome Block")
    _set_protect(client, block_project_id, protect_enabled=True, protect_max_req_per_min=1, protect_max_tok_per_min=1000)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(block_project_id, "openai"), total_tokens=1)
    block_before = int(_protect_metrics(client, block_project_id)["blocked_60m"])
    _decision(client, block_ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    block_metrics = _protect_metrics(client, block_project_id)
    block_after = int(block_metrics["blocked_60m"])
    assert block_after == block_before + 1
    assert block_metrics["last"] == {
        "decision": "block",
        "reason": "req_cap_breach",
        "source": "live",
        "ts": block_metrics["last"]["ts"],
    }
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


def test_timeout_report_reconciles_late_warn_decision_metrics(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Reconcile")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=200)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=170)

    request_id = "req-timeout-1"
    decision_response = client.post(
        "/api/v1/protect/decision",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 20},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "warn"

    timeout_response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"environment": "dev", "provider": "openai", "request_id": request_id},
    )
    assert timeout_response.status_code == 202

    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 1
    assert metrics["warned_60m"] == 0
    assert metrics["decision_timeouts_60m"] == 1
    assert metrics["last"] == {
        "decision": "allow",
        "reason": "decision_timeout",
        "source": "timeout_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_timeout_report_is_idempotent_per_request_id(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Idempotent")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="open")

    request_id = "req-timeout-idempotent"
    headers = {
        "X-Project-Ingest-Key": ingest_key,
        "X-Rheonic-Protect-Request-Id": request_id,
    }
    payload = {"environment": "dev", "provider": "openai", "request_id": request_id}

    first_response = client.post("/api/v1/protect/decision-timeout", headers=headers, json=payload)
    second_response = client.post("/api/v1/protect/decision-timeout", headers=headers, json=payload)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 1
    assert metrics["blocked_60m"] == 0
    assert metrics["decision_timeouts_60m"] == 1
    assert metrics["last"] == {
        "decision": "allow",
        "reason": "decision_timeout",
        "source": "timeout_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_timeout_report_records_block_when_project_fail_mode_is_closed(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Closed")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    timeout_response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev", "provider": "openai"},
    )

    assert timeout_response.status_code == 202
    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 0
    assert metrics["blocked_60m"] == 1
    assert metrics["decision_timeouts_60m"] == 1
    assert metrics["last"] == {
        "decision": "block",
        "reason": "decision_timeout",
        "source": "timeout_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_timeout_report_enqueues_fail_closed_protection_block_when_project_fail_mode_is_closed(tmp_path) -> None:
    dispatcher = FakeWebhookDispatcher()
    transport = FakeTransportService()
    client, _, _ = _make_client(tmp_path, webhook_dispatcher=dispatcher, transport_service=transport)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Closed Notify")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev", "provider": "openai"},
    )

    assert response.status_code == 202
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][1] == "protection.block"
    assert dispatcher.calls[0][2]["reason"] == "fail_closed"
    assert dispatcher.calls[0][2]["detail_reason"] == "decision_timeout"
    assert len(transport.calls) == 1
    assert transport.calls[0]["event_type"] == "protection.block"
    assert transport.calls[0]["template"] == "protection_block"
    _cleanup_overrides()


def test_unavailable_report_records_allow_when_project_fail_mode_is_open(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Unavailable Open")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="open")

    response = client.post(
        "/api/v1/protect/decision-unavailable",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev", "provider": "openai"},
    )

    assert response.status_code == 202
    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 1
    assert metrics["blocked_60m"] == 0
    assert metrics["decision_timeouts_60m"] == 0
    assert metrics["last"] == {
        "decision": "allow",
        "reason": "decision_unavailable",
        "source": "unavailable_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_unavailable_report_records_block_when_project_fail_mode_is_closed(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Unavailable Closed")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    response = client.post(
        "/api/v1/protect/decision-unavailable",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev", "provider": "openai"},
    )

    assert response.status_code == 202
    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 0
    assert metrics["blocked_60m"] == 1
    assert metrics["decision_timeouts_60m"] == 0
    assert metrics["last"] == {
        "decision": "block",
        "reason": "decision_unavailable",
        "source": "unavailable_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_unavailable_report_enqueues_fail_closed_protection_block_when_project_fail_mode_is_closed(tmp_path) -> None:
    dispatcher = FakeWebhookDispatcher()
    transport = FakeTransportService()
    client, _, _ = _make_client(tmp_path, webhook_dispatcher=dispatcher, transport_service=transport)
    project_id, ingest_key = _create_project_and_key(client, "Protect Unavailable Closed Notify")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    response = client.post(
        "/api/v1/protect/decision-unavailable",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev", "provider": "openai"},
    )

    assert response.status_code == 202
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0][1] == "protection.block"
    assert dispatcher.calls[0][2]["reason"] == "fail_closed"
    assert dispatcher.calls[0][2]["detail_reason"] == "decision_unavailable"
    assert len(transport.calls) == 1
    assert transport.calls[0]["event_type"] == "protection.block"
    assert transport.calls[0]["template"] == "protection_block"
    _cleanup_overrides()


def test_timeout_report_replaces_prior_allow_with_block_when_project_fail_mode_is_closed(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Closed Reconcile")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    request_id = "req-timeout-closed-allow"
    decision_response = client.post(
        "/api/v1/protect/decision",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 3},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "allow"

    timeout_response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"environment": "dev", "provider": "openai", "request_id": request_id},
    )

    assert timeout_response.status_code == 202
    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 0
    assert metrics["blocked_60m"] == 1
    assert metrics["decision_timeouts_60m"] == 1
    assert metrics["last"] == {
        "decision": "block",
        "reason": "decision_timeout",
        "source": "timeout_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_late_live_decision_is_ignored_after_timeout_fallback_finalizes_request(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Timeout Late Live")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    request_id = "req-timeout-late-live"
    timeout_response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"environment": "dev", "provider": "openai", "request_id": request_id},
    )
    assert timeout_response.status_code == 202

    decision_response = client.post(
        "/api/v1/protect/decision",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "allow"

    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 0
    assert metrics["blocked_60m"] == 1
    assert metrics["decision_timeouts_60m"] == 1
    assert metrics["last"] == {
        "decision": "block",
        "reason": "decision_timeout",
        "source": "timeout_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_late_live_decision_is_ignored_after_unavailable_fallback_finalizes_request(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Unavailable Late Live")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    request_id = "req-unavailable-late-live"
    unavailable_response = client.post(
        "/api/v1/protect/decision-unavailable",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"environment": "dev", "provider": "openai", "request_id": request_id},
    )
    assert unavailable_response.status_code == 202

    decision_response = client.post(
        "/api/v1/protect/decision",
        headers={
            "X-Project-Ingest-Key": ingest_key,
            "X-Rheonic-Protect-Request-Id": request_id,
        },
        json={"provider": "openai", "model": "gpt-4o-mini"},
    )
    assert decision_response.status_code == 200
    assert decision_response.json()["decision"] == "allow"

    metrics = _protect_metrics(client, project_id)
    assert metrics["allowed_60m"] == 0
    assert metrics["blocked_60m"] == 1
    assert metrics["decision_timeouts_60m"] == 0
    assert metrics["last"] == {
        "decision": "block",
        "reason": "decision_unavailable",
        "source": "unavailable_fallback",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_cooldown_active_finalizes_live_block_outcome(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path, cooldown_seconds=300)
    project_id, ingest_key = _create_project_and_key(client, "Protect Cooldown Live")
    _set_protect(client, project_id, protect_enabled=True, protect_max_req_per_min=1, protect_max_tok_per_min=1000)
    rolling_window.increment_project_60s(project_id=scoped_project_provider_id(project_id, "openai"), total_tokens=1)

    first_decision = _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    assert first_decision["decision"] == "block"
    assert first_decision["reason"] == "req_cap_breach"

    second_decision = _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    assert second_decision["decision"] == "block"
    assert second_decision["reason"] == "cooldown_active"

    metrics = _protect_metrics(client, project_id)
    assert metrics["blocked_60m"] == 2
    assert metrics["last"] == {
        "decision": "block",
        "reason": "cooldown_active",
        "source": "live",
        "ts": metrics["last"]["ts"],
    }
    _cleanup_overrides()


def test_protect_config_returns_project_fail_mode_and_server_timeout(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Config")
    _set_protect(client, project_id, protect_enabled=True, protect_fail_mode="closed")

    response = client.get(
        "/api/v1/protect/config",
        headers={"X-Project-Ingest-Key": ingest_key},
    )

    assert response.status_code == 200
    assert response.json() == {
        "protect_fail_mode": "closed",
        "protect_decision_timeout_ms": 150,
    }
    _cleanup_overrides()
