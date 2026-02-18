# Deterministic integration tests for anomaly baseline/spike/dedup flow.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.ingest_event_service import IngestEventService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.project_service import ProjectService
from app.dependencies import (
    get_current_user,
    get_detect_incidents_service,
    get_ingest_event_service,
    get_ingest_key_service,
    get_project_service,
)
from app.domain.models.event import Event
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.rolling_window import (
    RollingWindow,
    baseline_req_60s_key,
    baseline_tok_60s_key,
    incident_open_lock_key,
    requests_60s_key,
    tokens_60s_key,
)
from app.main import app


class FakeRedisClient:
    # In-memory fake for Redis operations used by rolling-window adapter.

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.lists: dict[str, list[object]] = {}

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
        to_delete: list[str] = []
        for member, score in zset.items():
            if score >= float(min_score) and score <= float(max_score):
                to_delete.append(member)
        for member in to_delete:
            del zset[member]
        return len(to_delete)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        zset = self.zsets.get(key, {})
        max_bound = float("inf") if max_score == float("inf") else float(max_score)
        items = [
            (member, score)
            for member, score in zset.items()
            if score >= float(min_score) and score <= max_bound
        ]
        items.sort(key=lambda item: (item[1], item[0]))
        return [member.encode("utf-8") for member, _ in items]

    def lpush(self, key: str, value: object) -> int:
        values = self.lists.setdefault(key, [])
        values.insert(0, value)
        return len(values)

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        values = self.lists.setdefault(key, [])
        if stop < 0:
            stop = len(values) + stop
        values[:] = values[start : stop + 1]
        return True

    def lrange(self, key: str, start: int, stop: int) -> list[object]:
        values = self.lists.get(key, [])
        if stop < 0:
            stop = len(values) + stop
        return values[start : stop + 1]

    def expire(self, key: str, ttl_seconds: int) -> bool:
        self.ttls[key] = ttl_seconds
        return True

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set_nx_ex(self, key: str, value: object, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        _ = value
        self.values[key] = 1
        self.ttls[key] = ttl_seconds
        return True

    def delete(self, key: str) -> int:
        deleted = 0
        if key in self.values:
            del self.values[key]
            deleted += 1
        if key in self.zsets:
            del self.zsets[key]
            deleted += 1
        if key in self.lists:
            del self.lists[key]
            deleted += 1
        return deleted


class DeterministicClock:
    # Shared deterministic clock used by rolling-window and ingest service.

    def __init__(self) -> None:
        self._current = datetime.fromtimestamp(1_000_000_000, tz=timezone.utc)

    def set_from_datetime(self, value: datetime) -> None:
        if value.tzinfo is None:
            self._current = value.replace(tzinfo=timezone.utc)
            return
        self._current = value.astimezone(timezone.utc)

    def now_datetime(self) -> datetime:
        return self._current

    def now_ms(self) -> int:
        return int(self._current.timestamp() * 1000)


class DeterministicIngestEventService(IngestEventService):
    # Ingest service that aligns processing time with event.ts for deterministic tests.

    def __init__(self, *args, clock: DeterministicClock, **kwargs) -> None:
        super().__init__(*args, now_provider=clock.now_datetime, **kwargs)
        self._clock = clock

    def ingest(self, event: Event) -> None:
        self._clock.set_from_datetime(event.ts)
        super().ingest(event)


def _cleanup_overrides() -> None:
    # Clear dependency overrides after test.
    app.dependency_overrides.clear()


def _event_payload(ts_seconds: int, total_tokens: int) -> dict[str, object]:
    # Build deterministic ingest payload with explicit timestamp.
    return {
        "ts": datetime.fromtimestamp(ts_seconds, tz=timezone.utc).isoformat(),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "environment": "dev",
        "response": {"total_tokens": total_tokens},
    }


def _list_open_incidents(client: TestClient, project_id: str) -> list[dict[str, object]]:
    # Read open incidents for the project.
    response = client.get("/api/v1/incidents", params={"project_id": project_id, "status": "open"})
    assert response.status_code == 200
    return response.json()


def _clear_project_redis_state(redis_client: FakeRedisClient, project_id: str) -> None:
    # Remove rolling-window and baseline keys used by this project.
    keys = [
        requests_60s_key(project_id),
        tokens_60s_key(project_id),
        baseline_req_60s_key(project_id),
        baseline_tok_60s_key(project_id),
        incident_open_lock_key(project_id, "burn_spike"),
        incident_open_lock_key(project_id, "request_spike"),
    ]
    for key in keys:
        redis_client.delete(key)


def _make_client(tmp_path) -> tuple[TestClient, FakeRedisClient]:
    # Build app client with deterministic ingest/anomaly dependencies.
    db_url = f"sqlite:///{tmp_path}/anomaly_flow.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    clock = DeterministicClock()
    redis_client = FakeRedisClient()
    rolling_window = RollingWindow(client=redis_client, now_ms_provider=clock.now_ms)
    project_repository = ProjectRepositoryImpl(session_factory=session_factory)
    incident_repository = IncidentRepositoryImpl(session_factory=session_factory)
    project_service = ProjectService(project_repository=project_repository)
    ingest_key_service = IngestKeyService(
        ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
        project_repository=project_repository,
    )
    ingest_event_service = DeterministicIngestEventService(
        event_repository=EventRepositoryImpl(session_factory=session_factory),
        realtime_counters=rolling_window,
        incident_repository=incident_repository,
        incident_severity_cache=None,
        baseline_window_count=30,
        incident_dedup_window_seconds=300,
        clock=clock,
    )
    detect_incidents_service = DetectIncidentsService(
        incident_repository=incident_repository,
        realtime_counters=rolling_window,
    )
    current_user = User(
        id="u-flow",
        email="flow@example.com",
        password_hash="hashed",
        created_at=datetime.fromtimestamp(1_000_000_000, tz=timezone.utc),
    )

    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_ingest_key_service] = lambda: ingest_key_service
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_event_service
    app.dependency_overrides[get_detect_incidents_service] = lambda: detect_incidents_service
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app), redis_client


def test_anomaly_baseline_spike_dedup_updates_existing_incident(tmp_path) -> None:
    # Build baseline, trigger spike incident, then dedupe-update same incident in window.
    client, redis_client = _make_client(tmp_path)
    base_ts = 1_000_000_000

    project = client.post("/api/v1/projects", json={"name": "Anomaly Flow Project"})
    assert project.status_code == 200
    project_id = project.json()["id"]
    _clear_project_redis_state(redis_client, project_id)

    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "dev"})
    assert key_response.status_code == 200
    plaintext_key = key_response.json()["key"]

    for i in range(10):
        response = client.post(
            "/api/v1/events",
            json=_event_payload(ts_seconds=base_ts + i, total_tokens=100),
            headers={"X-Project-Ingest-Key": plaintext_key},
        )
        assert response.status_code == 202

    assert _list_open_incidents(client, project_id) == []

    first_spike = client.post(
        "/api/v1/events",
        json=_event_payload(ts_seconds=base_ts + 20, total_tokens=60_000),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert first_spike.status_code == 202

    incidents_after_first = _list_open_incidents(client, project_id)
    assert len(incidents_after_first) == 1
    incident = incidents_after_first[0]
    evidence = incident["evidence"]
    assert evidence["baseline_tok_60s"] > 0
    assert evidence["current_tokens_60s"] >= 60_000
    assert evidence["tok_ratio"] >= 2
    assert evidence["count"] == 1
    assert evidence["last_seen"]
    incident_id = incident["id"]
    previous_last_seen = evidence["last_seen"]

    second_spike = client.post(
        "/api/v1/events",
        json=_event_payload(ts_seconds=base_ts + 30, total_tokens=70_000),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert second_spike.status_code == 202

    incidents_after_second = _list_open_incidents(client, project_id)
    assert len(incidents_after_second) == 1
    updated = incidents_after_second[0]
    assert updated["id"] == incident_id
    updated_evidence = updated["evidence"]
    assert updated_evidence["count"] == 2
    assert updated_evidence["last_seen"] > previous_last_seen
    assert updated_evidence["max_ratio_seen"] >= evidence["max_ratio_seen"]

    _clear_project_redis_state(redis_client, project_id)
    _cleanup_overrides()


def test_anomaly_severity_escalation_updates_or_creates(tmp_path) -> None:
    # Severity should escalate low->medium->high on stronger spikes within dedup window.
    client, redis_client = _make_client(tmp_path)
    base_ts = 1_000_000_000

    project = client.post("/api/v1/projects", json={"name": "Anomaly Severity Project"})
    assert project.status_code == 200
    project_id = project.json()["id"]
    _clear_project_redis_state(redis_client, project_id)

    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "staging"})
    assert key_response.status_code == 200
    plaintext_key = key_response.json()["key"]

    for i in range(10):
        response = client.post(
            "/api/v1/events",
            json=_event_payload(ts_seconds=base_ts + i, total_tokens=100),
            headers={"X-Project-Ingest-Key": plaintext_key},
        )
        assert response.status_code == 202

    low_spike = client.post(
        "/api/v1/events",
        json=_event_payload(ts_seconds=base_ts + 20, total_tokens=200),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert low_spike.status_code == 202
    incidents = _list_open_incidents(client, project_id)
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "low"
    assert 2 <= incidents[0]["evidence"]["tok_ratio"] < 5
    incident_id = incidents[0]["id"]
    low_last_seen = incidents[0]["evidence"]["last_seen"]

    medium_spike = client.post(
        "/api/v1/events",
        json=_event_payload(ts_seconds=base_ts + 30, total_tokens=4_000),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert medium_spike.status_code == 202
    incidents = _list_open_incidents(client, project_id)
    assert len(incidents) == 1
    assert incidents[0]["id"] == incident_id
    assert incidents[0]["severity"] == "medium"
    assert incidents[0]["evidence"]["count"] == 2
    assert incidents[0]["evidence"]["last_seen"] > low_last_seen

    high_spike = client.post(
        "/api/v1/events",
        json=_event_payload(ts_seconds=base_ts + 40, total_tokens=10_000),
        headers={"X-Project-Ingest-Key": plaintext_key},
    )
    assert high_spike.status_code == 202
    incidents = _list_open_incidents(client, project_id)
    assert len(incidents) == 1
    assert incidents[0]["id"] == incident_id
    assert incidents[0]["severity"] == "high"
    assert incidents[0]["evidence"]["count"] == 3
    assert incidents[0]["evidence"]["max_ratio_seen"] >= 10

    _clear_project_redis_state(redis_client, project_id)
    _cleanup_overrides()
