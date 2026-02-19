# Unit tests for rolling baselines and ingest anomaly intelligence.
from datetime import datetime, timedelta, timezone

from app.application.services.ingest_event_service import (
    IngestEventService,
    _severity_for_ratio,
)
from app.config import app_config
from app.domain.models.event import Event
from app.domain.models.incident import Incident
from app.infrastructure.redis.rolling_window import (
    RollingWindow,
    baseline_req_60s_key,
    baseline_tok_60s_key,
    median_or_zero,
    requests_60s_key,
    tokens_60s_key,
)


class FakeRedisClient:
    # In-memory fake for Redis list/sorted-set operations used by RollingWindow.

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


class FakeEventRepository:
    # In-memory sink for event persistence.

    def __init__(self) -> None:
        self.events: list[Event] = []

    def add(self, event: Event) -> None:
        self.events.append(event)

    def list_recent(self, project_id: str, limit: int = 100) -> list[Event]:
        _ = limit
        return [event for event in self.events if event.project_id == project_id]

    def purge_older_than(self, cutoff: datetime) -> int:
        original_count = len(self.events)
        self.events = [event for event in self.events if event.ts >= cutoff]
        return original_count - len(self.events)


class FakeRealtimeCounterStore:
    # Deterministic realtime counter store for incident logic tests.

    def __init__(
        self,
        snapshots: list[tuple[int, int]],
        baselines: list[tuple[float, float]],
    ) -> None:
        self._snapshots = snapshots
        self._baselines = baselines
        self.increment_calls: list[tuple[str, int]] = []

    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        self.increment_calls.append((project_id, total_tokens))

    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        _ = project_id
        return self._snapshots.pop(0)

    def record_baseline_snapshot(
        self,
        project_id: str,
        requests_60s: int,
        tokens_60s: int,
        max_windows: int,
    ) -> tuple[float, float]:
        _ = project_id, requests_60s, tokens_60s, max_windows
        return self._baselines.pop(0)

    def acquire_incident_lock(self, project_id: str, incident_type: str, ttl_seconds: int) -> bool:
        _ = project_id, incident_type, ttl_seconds
        return True

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        _ = project_id, incident_type


class FakeIncidentRepository:
    # In-memory incident repo with dedup update behavior.

    def __init__(self) -> None:
        self.incidents: list[Incident] = []
        self.created_count = 0
        self.updated_count = 0

    def create_incident(self, incident: Incident) -> Incident:
        self.incidents.append(incident)
        self.created_count += 1
        return incident

    def get_open_incident_by_type(self, project_id: str, incident_type: str) -> Incident | None:
        for incident in reversed(self.incidents):
            if incident.project_id == project_id and incident.incident_type == incident_type and incident.status == "open":
                return incident
        return None

    def get_open_incident_by_fingerprint(
        self,
        project_id: str,
        fingerprint: str,
        created_after: datetime,
    ) -> Incident | None:
        for incident in reversed(self.incidents):
            if (
                incident.project_id == project_id
                and incident.status == "open"
                and incident.fingerprint == fingerprint
                and incident.created_at >= created_after
            ):
                return incident
        return None

    def update_open_incident_activity(
        self,
        incident_id: str,
        evidence: dict[str, object],
        last_seen_at: datetime,
        severity: str,
    ) -> Incident | None:
        for index, incident in enumerate(self.incidents):
            if incident.id != incident_id or incident.status != "open":
                continue
            updated = Incident(
                id=incident.id,
                project_id=incident.project_id,
                incident_type=incident.incident_type,
                severity=severity,
                status=incident.status,
                created_at=incident.created_at,
                resolved_at=incident.resolved_at,
                evidence=evidence,
                fingerprint=incident.fingerprint,
                last_seen_at=last_seen_at,
            )
            self.incidents[index] = updated
            self.updated_count += 1
            return updated
        return None

    def list_by_project(self, project_id: str, status: str = "open") -> list[Incident]:
        return [incident for incident in self.incidents if incident.project_id == project_id and incident.status == status]

    def get_by_id(self, incident_id: str) -> Incident | None:
        for incident in self.incidents:
            if incident.id == incident_id:
                return incident
        return None

    def resolve_incident(self, incident_id: str) -> Incident | None:
        for index, incident in enumerate(self.incidents):
            if incident.id != incident_id:
                continue
            updated = Incident(
                id=incident.id,
                project_id=incident.project_id,
                incident_type=incident.incident_type,
                severity=incident.severity,
                status="resolved",
                created_at=incident.created_at,
                resolved_at=datetime.now(timezone.utc),
                evidence=incident.evidence,
                fingerprint=incident.fingerprint,
                last_seen_at=incident.last_seen_at,
            )
            self.incidents[index] = updated
            return updated
        return None


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


def _build_event(project_id: str, total_tokens: int = 0) -> Event:
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


def _make_now_provider(values: list[datetime]):
    # Build deterministic datetime provider.
    state = {"index": 0}

    def _provider() -> datetime:
        index = state["index"]
        state["index"] = min(index + 1, len(values) - 1)
        return values[index]

    return _provider


def test_realtime_counter_keys_match_required_format() -> None:
    # Counter key helpers must match required Redis key format exactly.
    project_id = "project_123"
    assert requests_60s_key(project_id) == "rt:project_123:req:z"
    assert tokens_60s_key(project_id) == "rt:project_123:tok:z"
    assert baseline_req_60s_key(project_id) == "bl:project_123:req"
    assert baseline_tok_60s_key(project_id) == "bl:project_123:tok"


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


def test_record_baseline_snapshot_returns_median_and_zero_for_empty_helper() -> None:
    # Baseline snapshot should be median of list values and helper handles empty.
    client = FakeRedisClient()
    rolling_window = RollingWindow(client=client)
    for req, tok in [(2, 10), (8, 30), (4, 20), (20, 200), (6, 25)]:
        baseline_req, baseline_tok = rolling_window.record_baseline_snapshot(
            project_id="p1",
            requests_60s=req,
            tokens_60s=tok,
            max_windows=30,
        )
    assert baseline_req == 6.0
    assert baseline_tok == 25.0
    assert median_or_zero([]) == 0.0


def test_ratio_to_severity_mapping() -> None:
    # Ratio mapping should use low/medium/high cutoffs at 2/5/10.
    assert _severity_for_ratio(2.0) == "low"
    assert _severity_for_ratio(4.99) == "low"
    assert _severity_for_ratio(5.0) == "medium"
    assert _severity_for_ratio(9.99) == "medium"
    assert _severity_for_ratio(10.0) == "high"


def test_dedup_updates_incident_within_window_and_creates_after_window() -> None:
    # First spike creates, second in dedup window updates, later spike creates new row.
    t0 = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=120)
    t2 = t0 + timedelta(seconds=700)
    realtime = FakeRealtimeCounterStore(
        snapshots=[(3, 100), (4, 120), (6, 140)],
        baselines=[(1.0, 10.0), (1.0, 10.0), (1.0, 10.0)],
    )
    incidents = FakeIncidentRepository()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=realtime,  # type: ignore[arg-type]
        incident_repository=incidents,  # type: ignore[arg-type]
        incident_severity_cache=None,
        baseline_window_count=30,
        incident_dedup_window_seconds=300,
        now_provider=_make_now_provider([t0, t1, t2]),
    )

    service.ingest(_build_event(project_id="p1"))
    service.ingest(_build_event(project_id="p1"))
    service.ingest(_build_event(project_id="p1"))

    assert incidents.created_count == 2
    assert incidents.updated_count == 1
    assert len(incidents.incidents) == 2
    first_incident = incidents.incidents[0]
    assert first_incident.evidence["count"] == 2
    assert first_incident.evidence["max_ratio_seen"] == 12.0


def test_both_spikes_create_single_burn_spike_with_both_ratios() -> None:
    # When requests and tokens both spike, create one burn_spike incident with both ratios.
    now = datetime(2026, 2, 18, 12, 0, tzinfo=timezone.utc)
    realtime = FakeRealtimeCounterStore(
        snapshots=[(10, 200)],
        baselines=[(1.0, 10.0)],
    )
    incidents = FakeIncidentRepository()
    service = IngestEventService(
        event_repository=FakeEventRepository(),
        realtime_counters=realtime,  # type: ignore[arg-type]
        incident_repository=incidents,  # type: ignore[arg-type]
        incident_severity_cache=None,
        baseline_window_count=30,
        incident_dedup_window_seconds=300,
        now_provider=_make_now_provider([now]),
    )

    service.ingest(_build_event(project_id="p1"))

    assert len(incidents.incidents) == 1
    incident = incidents.incidents[0]
    assert incident.incident_type == "burn_spike"
    assert incident.evidence["req_ratio"] == 10.0
    assert incident.evidence["tok_ratio"] == 20.0
