# Unit tests for event-ingest Redis realtime counters.
from datetime import datetime, timezone

from app.application.services.ingest_event_service import IngestEventService
from app.config import app_config
from app.domain.models.event import Event
from app.infrastructure.redis.rolling_window import (
    RollingWindow,
    incident_open_lock_key,
    normalize_total_tokens,
    requests_60s_key,
    tokens_60s_key,
)


class FakeRedisClient:
    # Simple in-memory fake for Redis counter operations.

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.zsets: dict[str, dict[str, int]] = {}

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

    def expire(self, key: str, ttl_seconds: int) -> bool:
        self.ttls[key] = ttl_seconds
        return True

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
        return deleted


class FakeEventRepository:
    # In-memory event sink for ingest service tests.
    def __init__(self) -> None:
        self.events: list[Event] = []

    def add(self, event: Event) -> None:
        self.events.append(event)


class FakeIncidentRepository:
    # In-memory incident sink for ingest service tests.
    def __init__(self) -> None:
        self.incidents: list[object] = []

    def create_incident(self, incident: object) -> object:
        self.incidents.append(incident)
        return incident


def _make_time_provider(values: list[int]):
    # Build deterministic millisecond time provider.
    state = {"index": 0}

    def _provider() -> int:
        index = state["index"]
        state["index"] = min(index + 1, len(values) - 1)
        return values[index]

    return _provider


def _make_id_provider(values: list[str]):
    # Build deterministic member id provider.
    state = {"index": 0}

    def _provider() -> str:
        index = state["index"]
        state["index"] = min(index + 1, len(values) - 1)
        return values[index]

    return _provider


def test_realtime_counter_keys_match_required_format() -> None:
    # Counter key helpers must match required Redis key format exactly.
    project_id = "project_123"
    assert requests_60s_key(project_id) == "rt:project_123:req:z"
    assert tokens_60s_key(project_id) == "rt:project_123:tok:z"


def test_increment_project_60s_updates_rolling_count_sum_and_ttls() -> None:
    # Rolling-window updates should preserve count/sum and set cleanup TTL.
    client = FakeRedisClient()
    rolling_window = RollingWindow(
        client=client,
        now_ms_provider=_make_time_provider([1_000, 2_000, 2_000]),
        member_id_provider=_make_id_provider(["a", "b"]),
    )

    rolling_window.increment_project_60s(project_id="p1", total_tokens=42)
    rolling_window.increment_project_60s(project_id="p1", total_tokens=8)

    requests_60s, tokens_60s = rolling_window.get_project_60s("p1")

    assert requests_60s == 2
    assert tokens_60s == 50
    assert client.ttls["rt:p1:req:z"] == app_config.rolling_counter_ttl_seconds
    assert client.ttls["rt:p1:tok:z"] == app_config.rolling_counter_ttl_seconds


def test_get_project_60s_excludes_points_older_than_60s() -> None:
    # Points outside last 60 seconds must be excluded.
    client = FakeRedisClient()
    rolling_window = RollingWindow(
        client=client,
        now_ms_provider=_make_time_provider([1_000, 61_001, 61_001]),
        member_id_provider=_make_id_provider(["old", "new"]),
    )

    rolling_window.increment_project_60s(project_id="p1", total_tokens=10)
    rolling_window.increment_project_60s(project_id="p1", total_tokens=30)

    requests_60s, tokens_60s = rolling_window.get_project_60s("p1")

    assert requests_60s == 1
    assert tokens_60s == 30


def test_get_project_60s_returns_zero_for_missing_keys() -> None:
    # Reading counters should default to zero when keys do not exist.
    rolling_window = RollingWindow(client=FakeRedisClient())
    assert rolling_window.get_project_60s("missing") == (0, 0)


def test_normalize_total_tokens_defaults_none_to_zero() -> None:
    # Missing total_tokens should be normalized to zero.
    assert normalize_total_tokens(None) == 0
    assert normalize_total_tokens(10) == 10


def _build_event(project_id: str, total_tokens: int) -> Event:
    # Build deterministic event fixture for ingest service tests.
    now = datetime.now(timezone.utc)
    return Event(
        id="evt-1",
        ts=now,
        project_id=project_id,
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        input_tokens=0,
        output_tokens=0,
        total_tokens=total_tokens,
        latency_ms=10,
        status="ok",
        error_type=None,
        http_status=200,
        created_at=now,
    )


def test_ingest_below_thresholds_creates_no_incident() -> None:
    # Below-threshold counters should not produce incidents.
    redis_client = FakeRedisClient()
    realtime = RollingWindow(client=redis_client)
    incident_repo = FakeIncidentRepository()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=realtime,
        incident_repository=incident_repo,  # type: ignore[arg-type]
        threshold_tokens_60s=100,
        threshold_req_60s=10,
        incident_lock_ttl_seconds=1800,
    )

    service.ingest(_build_event(project_id="p1", total_tokens=10))
    assert len(incident_repo.incidents) == 0


def test_ingest_tokens_threshold_creates_incident_once() -> None:
    # Crossing tokens threshold should create one burn_spike incident.
    redis_client = FakeRedisClient()
    realtime = RollingWindow(client=redis_client)
    incident_repo = FakeIncidentRepository()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=realtime,
        incident_repository=incident_repo,  # type: ignore[arg-type]
        threshold_tokens_60s=50,
        threshold_req_60s=200,
        incident_lock_ttl_seconds=1800,
    )

    service.ingest(_build_event(project_id="p1", total_tokens=60))
    assert len(incident_repo.incidents) == 1
    assert incident_repo.incidents[0].incident_type == "burn_spike"  # type: ignore[attr-defined]


def test_ingest_second_event_within_lock_window_skips_duplicate_incident() -> None:
    # Second threshold breach while lock exists should not create duplicate incident.
    redis_client = FakeRedisClient()
    realtime = RollingWindow(client=redis_client)
    incident_repo = FakeIncidentRepository()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=realtime,
        incident_repository=incident_repo,  # type: ignore[arg-type]
        threshold_tokens_60s=50,
        threshold_req_60s=200,
        incident_lock_ttl_seconds=1800,
    )

    service.ingest(_build_event(project_id="p1", total_tokens=60))
    service.ingest(_build_event(project_id="p1", total_tokens=70))

    assert len(incident_repo.incidents) == 1
    assert incident_open_lock_key("p1", "burn_spike") in redis_client.values
