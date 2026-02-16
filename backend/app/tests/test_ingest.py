# Unit tests for event-ingest Redis realtime counters.
from app.infrastructure.redis.rolling_window import (
    COUNTER_TTL_SECONDS,
    RollingWindow,
    normalize_total_tokens,
    requests_60s_key,
    tokens_60s_key,
)


class FakeRedisClient:
    # Simple in-memory fake for Redis counter operations.

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def incrby(self, key: str, amount: int) -> int:
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    def expire(self, key: str, ttl_seconds: int) -> bool:
        self.ttls[key] = ttl_seconds
        return True

    def get(self, key: str) -> object | None:
        value = self.values.get(key)
        if value is None:
            return None
        return str(value).encode("utf-8")


def test_realtime_counter_keys_match_required_format() -> None:
    # Counter key helpers must match required Redis key format exactly.
    project_id = "project_123"
    assert requests_60s_key(project_id) == "rt:project_123:req:60s"
    assert tokens_60s_key(project_id) == "rt:project_123:tok:60s"


def test_increment_project_60s_updates_counts_and_ttls() -> None:
    # Incrementing project counters should update values and TTL=120s.
    client = FakeRedisClient()
    rolling_window = RollingWindow(client=client)

    rolling_window.increment_project_60s(project_id="p1", total_tokens=42)
    rolling_window.increment_project_60s(project_id="p1", total_tokens=8)

    assert client.values["rt:p1:req:60s"] == 2
    assert client.values["rt:p1:tok:60s"] == 50
    assert client.ttls["rt:p1:req:60s"] == COUNTER_TTL_SECONDS
    assert client.ttls["rt:p1:tok:60s"] == COUNTER_TTL_SECONDS


def test_get_project_60s_returns_zero_for_missing_keys() -> None:
    # Reading counters should default to zero when keys do not exist.
    rolling_window = RollingWindow(client=FakeRedisClient())
    assert rolling_window.get_project_60s("missing") == (0, 0)


def test_normalize_total_tokens_defaults_none_to_zero() -> None:
    # Missing total_tokens should be normalized to zero.
    assert normalize_total_tokens(None) == 0
    assert normalize_total_tokens(10) == 10
