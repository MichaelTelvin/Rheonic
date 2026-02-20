# API tests for protect preflight decision endpoint.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.metrics_service import MetricsService
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
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.infrastructure.redis.rolling_window import RollingWindow
from app.main import app


class FakeRedisClient:
    # In-memory fake redis adapter for rolling counters + severity cache.

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
    protect_action_store = ProtectActionStore(redis_client=redis_client)  # type: ignore[arg-type]
    protect_service = ProtectService(
        ingest_key_service=ingest_key_service,
        realtime_counters=rolling_window,
        incident_severity_cache=incident_severity_cache,
        protect_action_store=protect_action_store,
    )
    metrics_service = MetricsService(
        realtime_counters=rolling_window,
        protect_action_store=protect_action_store,
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


def _decision(client: TestClient, ingest_key: str, body: dict[str, object] | None = None) -> dict[str, object]:
    response = client.post(
        "/api/v1/protect/decision",
        headers={"X-Project-Ingest-Key": ingest_key},
        json=body or {"provider": "openai", "model": "gpt-4o-mini"},
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
    assert snapshot["threshold_req_60s"] == 10
    assert snapshot["threshold_tok_60s"] == 500
    assert snapshot["decision_timeout_ms"] == 250
    assert decision["protect_decision_timeout_ms"] == 250
    assert snapshot["predictive"]["enabled"] is False
    assert snapshot["predictive"]["estimated_next_tokens"] is None
    assert snapshot["predictive"]["would_exceed_tokens_cap"] is False
    _cleanup_overrides()


def test_predictive_near_cap_warns_when_next_call_would_reach_cap(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Predictive Warn")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=50_000)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=49_000)

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_output_tokens": 2_000,
            "input_tokens_estimate": 0,
        },
    )

    assert decision["decision"] == "warn"
    assert decision["reason"] == "predictive_near_cap"
    snapshot = decision["snapshot"]
    assert snapshot["predictive"]["enabled"] is True
    assert snapshot["predictive"]["estimated_next_tokens"] == 2_000
    assert snapshot["predictive"]["would_exceed_tokens_cap"] is True
    _cleanup_overrides()


def test_predictive_warn_works_with_input_estimate_only(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Predictive Input Only")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=50_000)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=49_000)

    decision = _decision(
        client,
        ingest_key,
        body={"provider": "openai", "model": "gpt-4o-mini", "input_tokens_estimate": 1_000},
    )

    assert decision["decision"] == "warn"
    assert decision["reason"] == "predictive_near_cap"
    snapshot = decision["snapshot"]
    assert snapshot["predictive"]["enabled"] is True
    assert snapshot["predictive"]["estimated_next_tokens"] == 1_000
    assert snapshot["predictive"]["would_exceed_tokens_cap"] is True
    _cleanup_overrides()


def test_missing_input_tokens_estimate_skips_predictive_warn(tmp_path) -> None:
    client, rolling_window, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Predictive Missing Input Estimate")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=50_000)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=49_000)

    response = client.post(
        "/api/v1/protect/decision",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_output_tokens": 2_000,
        },
    )
    assert response.status_code == 200
    decision = response.json()
    assert decision["decision"] == "allow"
    assert decision["reason"] == "ok"
    assert decision["snapshot"]["predictive"]["enabled"] is False
    assert decision["snapshot"]["predictive"]["estimated_next_tokens"] is None
    assert decision["snapshot"]["predictive"]["would_exceed_tokens_cap"] is False
    _cleanup_overrides()


def test_predictive_warn_does_not_override_high_incident_block(tmp_path) -> None:
    client, rolling_window, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Predictive High Incident")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=50_000)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=49_000)
    severity_cache.set(project_id, "high")

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_output_tokens": 2_000,
            "input_tokens_estimate": 0,
        },
    )

    assert decision["decision"] == "block"
    assert decision["reason"] == "incident_high"
    _cleanup_overrides()


def test_predictive_warn_does_not_override_medium_incident_warn_reason(tmp_path) -> None:
    client, rolling_window, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Predictive Medium Incident")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=50_000)
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=49_000)
    severity_cache.set(project_id, "medium")

    decision = _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_output_tokens": 2_000,
            "input_tokens_estimate": 0,
        },
    )

    assert decision["decision"] == "warn"
    assert decision["reason"] == "incident_medium"
    _cleanup_overrides()


def test_missing_incident_severity_defaults_to_none(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Severity Missing")
    _set_protect(client, project_id, protect_enabled=True)
    decision = _decision(client, ingest_key)
    assert decision["snapshot"]["incident_severity"] == "none"
    _cleanup_overrides()


def test_protect_metrics_defaults_and_allow_keeps_counters_zero(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Metrics Counter")
    _set_protect(client, project_id, protect_enabled=True)

    baseline = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert baseline.status_code == 200
    assert baseline.json() == {
        "allowed_60m": 0,
        "warned_60m": 0,
        "blocked_60m": 0,
        "decision_timeouts_60m": 0,
        "last": None,
        "decision_latency_p50_60m_ms": None,
        "decision_latency_p95_60m_ms": None,
    }

    _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    after_allow = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert after_allow.status_code == 200
    payload = after_allow.json()
    assert payload["allowed_60m"] == 1
    assert payload["warned_60m"] == 0
    assert payload["blocked_60m"] == 0
    assert payload["decision_timeouts_60m"] == 0
    assert payload["last"]["decision"] == "allow"
    assert payload["last"]["reason"] == "ok"
    assert isinstance(payload["decision_latency_p50_60m_ms"], int)
    assert isinstance(payload["decision_latency_p95_60m_ms"], int)
    _cleanup_overrides()


def test_protect_metrics_increment_on_warn_and_block(tmp_path) -> None:
    client, rolling_window, severity_cache = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Metrics Counter 2")
    _set_protect(client, project_id, protect_enabled=True, protect_max_tok_per_min=1000)

    severity_cache.set(project_id, "medium")
    warn_decision = _decision(client, ingest_key)
    assert warn_decision["decision"] == "warn"

    severity_cache.set(project_id, "none")
    rolling_window.increment_project_60s(project_id=project_id, total_tokens=1000)
    _decision(
        client,
        ingest_key,
        body={
            "provider": "openai",
            "model": "gpt-4o-mini",
            "max_output_tokens": 2_000,
            "input_tokens_estimate": 0,
        },
    )

    metrics_response = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["allowed_60m"] == 0
    assert payload["warned_60m"] == 1
    assert payload["blocked_60m"] == 1
    assert payload["decision_timeouts_60m"] == 0
    assert payload["last"]["decision"] == "block"
    assert payload["last"]["reason"] == "tok_limit"
    assert isinstance(payload["decision_latency_p50_60m_ms"], int)
    assert isinstance(payload["decision_latency_p95_60m_ms"], int)
    _cleanup_overrides()


def test_protect_latency_percentiles_are_windowed_and_deterministic(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, _ = _create_project_and_key(client, "Protect Latency Percentiles")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    redis_client: FakeRedisClient = app.dependency_overrides[get_metrics_service]()._protect_action_store._redis_client  # type: ignore[attr-defined]
    latency_key = f"pa:{project_id}:latency:60m"
    redis_client.zadd(
        latency_key,
        {
            f"{now_ms - 60_000}:a:10": now_ms - 60_000,
            f"{now_ms - 30_000}:b:20": now_ms - 30_000,
            f"{now_ms - 20_000}:c:30": now_ms - 20_000,
            f"{now_ms - 10_000}:d:40": now_ms - 10_000,
            f"{now_ms - 3_700_000}:old:999": now_ms - 3_700_000,
        },
    )
    response = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision_latency_p50_60m_ms"] == 20
    assert payload["decision_latency_p95_60m_ms"] == 40
    _cleanup_overrides()


def test_protect_latency_record_applies_ttl(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Latency TTL")
    _set_protect(client, project_id, protect_enabled=True)
    _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})

    redis_client: FakeRedisClient = app.dependency_overrides[get_metrics_service]()._protect_action_store._redis_client  # type: ignore[attr-defined]
    assert redis_client.ttls.get(f"pa:{project_id}:latency:60m") == 3600
    _cleanup_overrides()


def test_protect_health_metrics_shape_and_values(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Health")
    _set_protect(client, project_id, protect_enabled=True)

    baseline = client.get(f"/api/v1/metrics/protect/health?project_id={project_id}")
    assert baseline.status_code == 200
    assert baseline.json() == {"p50_ms": None, "p95_ms": None, "timeouts_60m": 0}

    _decision(client, ingest_key, body={"provider": "openai", "model": "gpt-4o-mini"})
    response = client.get(f"/api/v1/metrics/protect/health?project_id={project_id}")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"p50_ms", "p95_ms", "timeouts_60m"}
    assert isinstance(payload["timeouts_60m"], int)
    assert payload["timeouts_60m"] == 0
    assert isinstance(payload["p50_ms"], int)
    assert isinstance(payload["p95_ms"], int)
    _cleanup_overrides()


def test_protect_health_requires_auth(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, _ = _create_project_and_key(client, "Protect Health Auth")
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get(f"/api/v1/metrics/protect/health?project_id={project_id}")
    assert response.status_code == 401
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


def test_decision_timeout_endpoint_increments_counter_and_metrics(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    project_id, ingest_key = _create_project_and_key(client, "Protect Decision Timeout Counter")

    first = client.post(
        "/api/v1/protect/decision-timeout",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev"},
    )
    assert first.status_code == 202
    assert first.json() == {"status": "accepted"}

    second = client.post(
        "/api/v1/protect/decision-timeout",
        headers={"X-Project-Ingest-Key": ingest_key},
        json={"environment": "dev"},
    )
    assert second.status_code == 202

    metrics_response = client.get(f"/api/v1/metrics/protect?project_id={project_id}")
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["decision_timeouts_60m"] == 2
    _cleanup_overrides()


def test_decision_timeout_endpoint_rejects_invalid_ingest_key(tmp_path) -> None:
    client, _, _ = _make_client(tmp_path)
    response = client.post(
        "/api/v1/protect/decision-timeout",
        headers={"X-Project-Ingest-Key": "invalid"},
        json={"environment": "dev"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "invalid ingest key"
    _cleanup_overrides()
