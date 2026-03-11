from __future__ import annotations

from app.infrastructure.redis.protect_action_store import ProtectActionStore


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    def get(self, key: str) -> object | None:
        return self.values.get(key)


def test_set_block_cooldown_uses_redis_wrapper_signature() -> None:
    redis_client = _FakeRedisClient()
    store = ProtectActionStore(redis_client=redis_client)  # type: ignore[arg-type]

    store.set_block_cooldown(project_id="project-1:openai", blocked_until_ms=1_700_000_000_000, cooldown_seconds=90)

    assert redis_client.values["protect:cooldown:project-1:openai"] == "1700000000000"
    assert redis_client.ttls["protect:cooldown:project-1:openai"] == 90
    assert store.get_block_cooldown_until_ms("project-1:openai") == 1_700_000_000_000
