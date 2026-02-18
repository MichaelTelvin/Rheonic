# API tests for ingest idempotency and rate limiting hardening.
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.application.services.ingest_event_service import IngestEventService
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.metrics_service import MetricsService
from app.application.services.project_service import ProjectService
from app.config import Settings
from app.dependencies import (
    get_current_user,
    get_ingest_event_service,
    get_ingest_key_service,
    get_metrics_service,
    get_project_service,
    get_redis_client,
    get_settings,
)
from app.domain.models.user import User
from app.infrastructure.db.base import DatabaseSessionFactory
from app.infrastructure.db.models import Base, EventRecord
from app.infrastructure.db.repositories.event_repository_impl import EventRepositoryImpl
from app.infrastructure.db.repositories.incident_repository_impl import IncidentRepositoryImpl
from app.infrastructure.db.repositories.ingest_key_repository_impl import IngestKeyRepositoryImpl
from app.infrastructure.db.repositories.project_repository_impl import ProjectRepositoryImpl
from app.infrastructure.redis.rolling_window import RollingWindow
from app.main import app


class FakeRedisClient:
    # In-memory fake for Redis operations used in ingest and metrics paths.

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.lists: dict[str, list[object]] = {}

    def set_nx_ex(self, key: str, value: object, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        _ = value
        self.values[key] = 1
        self.ttls[key] = ttl_seconds
        return True

    def incr(self, key: str) -> int:
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    def expire(self, key: str, ttl_seconds: int) -> bool:
        self.ttls[key] = ttl_seconds
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
        to_delete = [member for member, score in zset.items() if score >= float(min_score) and score <= float(max_score)]
        for member in to_delete:
            del zset[member]
        return len(to_delete)

    def zcard(self, key: str) -> int:
        return len(self.zsets.get(key, {}))

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        zset = self.zsets.get(key, {})
        max_bound = float("inf") if max_score == float("inf") else float(max_score)
        items = [(member, score) for member, score in zset.items() if score >= float(min_score) and score <= max_bound]
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


def _cleanup_overrides() -> None:
    # Reset dependency overrides after each test.
    app.dependency_overrides.clear()


def _event_payload(total_tokens: int) -> dict[str, object]:
    # Build a minimal valid ingest payload.
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "provider": "openai",
        "model": "gpt-4o-mini",
        "environment": "dev",
        "response": {"total_tokens": total_tokens},
    }


def _make_client(tmp_path, settings: Settings | None = None) -> tuple[TestClient, DatabaseSessionFactory]:
    # Build test client with real ingest service and in-memory Redis adapter.
    db_url = f"sqlite:///{tmp_path}/ingest_hardening_test.db"
    session_factory = DatabaseSessionFactory(database_url=db_url)
    Base.metadata.create_all(bind=session_factory.engine)

    redis_client = FakeRedisClient()
    rolling_window = RollingWindow(client=redis_client)
    project_repository = ProjectRepositoryImpl(session_factory=session_factory)
    project_service = ProjectService(project_repository=project_repository)
    ingest_key_service = IngestKeyService(
        ingest_key_repository=IngestKeyRepositoryImpl(session_factory=session_factory),
        project_repository=project_repository,
    )
    ingest_service = IngestEventService(
        event_repository=EventRepositoryImpl(session_factory=session_factory),
        realtime_counters=rolling_window,
        incident_repository=IncidentRepositoryImpl(session_factory=session_factory),
        incident_severity_cache=None,
        baseline_window_count=30,
        incident_dedup_window_seconds=300,
    )
    metrics_service = MetricsService(realtime_counters=rolling_window)

    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_ingest_key_service] = lambda: ingest_key_service
    app.dependency_overrides[get_ingest_event_service] = lambda: ingest_service
    app.dependency_overrides[get_metrics_service] = lambda: metrics_service
    app.dependency_overrides[get_redis_client] = lambda: redis_client
    app.dependency_overrides[get_settings] = lambda: settings or Settings(app_env="dev")
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u-hardening",
        email="hardening@example.com",
        password_hash="hashed",
        created_at=datetime.now(timezone.utc),
    )
    return TestClient(app), session_factory


def test_ingest_idempotency_skips_duplicate_insert_and_counter_update(tmp_path) -> None:
    # Same idempotency key should process once; new key should process again.
    client, session_factory = _make_client(tmp_path)

    project_response = client.post("/api/v1/projects", json={"name": "Idempotency Project"})
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "dev"})
    assert key_response.status_code == 200
    plaintext_key = key_response.json()["key"]

    first = client.post(
        "/api/v1/events",
        json=_event_payload(total_tokens=50),
        headers={"X-Project-Ingest-Key": plaintext_key, "Idempotency-Key": "idem-1"},
    )
    second = client.post(
        "/api/v1/events",
        json=_event_payload(total_tokens=50),
        headers={"X-Project-Ingest-Key": plaintext_key, "Idempotency-Key": "idem-1"},
    )
    third = client.post(
        "/api/v1/events",
        json=_event_payload(total_tokens=50),
        headers={"X-Project-Ingest-Key": plaintext_key, "Idempotency-Key": "idem-2"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert third.status_code == 202

    with session_factory.create_session() as session:
        stored_events = session.query(EventRecord).filter(EventRecord.project_id == project_id).all()
        assert len(stored_events) == 2

    metrics = client.get(f"/api/v1/metrics/realtime?project_id={project_id}")
    assert metrics.status_code == 200
    assert metrics.json()["requests_60s"] == 2
    assert metrics.json()["tokens_60s"] == 100

    _cleanup_overrides()


def test_ingest_rate_limit_returns_429_when_exceeded(tmp_path) -> None:
    # Requests beyond configured per-minute limit should be rejected.
    client, _ = _make_client(
        tmp_path,
        settings=Settings(app_env="dev", ingest_rate_limit_per_minute=3),
    )

    project_response = client.post("/api/v1/projects", json={"name": "RateLimit Project"})
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    key_response = client.post(f"/api/v1/projects/{project_id}/keys", json={"name": "prod"})
    assert key_response.status_code == 200
    plaintext_key = key_response.json()["key"]

    responses = []
    for _ in range(4):
        responses.append(
            client.post(
                "/api/v1/events",
                json=_event_payload(total_tokens=10),
                headers={"X-Project-Ingest-Key": plaintext_key},
            )
        )

    statuses = [response.status_code for response in responses]
    assert statuses[:3] == [202, 202, 202]
    assert statuses[3] == 429
    assert responses[3].json() == {"error": {"code": "too_many_requests", "message": "rate limit exceeded"}}

    _cleanup_overrides()
