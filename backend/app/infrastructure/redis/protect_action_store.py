# Redis-backed protect decision audit counters for dashboard visibility.
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.redis.redis_client import RedisClient
from app.logger import get_logger

logger = get_logger(__name__)

_COUNTER_TTL_SECONDS = 3600


def _warn_key(project_id: str) -> str:
    return f"pa:{project_id}:warn:60m"


def _block_key(project_id: str) -> str:
    return f"pa:{project_id}:block:60m"


def _last_key(project_id: str) -> str:
    return f"pa:{project_id}:last"


class ProtectActionStore:
    # Stores protect decision counters and last decision snapshot in Redis.

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    def record(self, project_id: str, decision: str, reason: str, ts: datetime | None = None) -> None:
        # Record warn/block counters and keep the last decision payload for UI.
        timestamp = (ts or datetime.now(timezone.utc)).isoformat()
        try:
            if decision == "warn":
                self._increment_with_ttl(_warn_key(project_id))
            elif decision == "block":
                self._increment_with_ttl(_block_key(project_id))

            payload = {"decision": decision, "reason": reason, "ts": timestamp}
            self._redis_client.set(_last_key(project_id), json.dumps(payload), ex=_COUNTER_TTL_SECONDS)
        except Exception:
            logger.warning("Failed recording protect decision counters", extra={"project_id": project_id})

    def get_metrics(self, project_id: str) -> dict[str, Any]:
        # Read 60-minute protect decision counters and last decision snapshot.
        try:
            warn = self._read_int(_warn_key(project_id))
            block = self._read_int(_block_key(project_id))
            last_raw = self._redis_client.get(_last_key(project_id))
            return {
                "warn_60m": warn,
                "block_60m": block,
                "last": self._parse_last(last_raw),
            }
        except Exception:
            logger.warning("Failed reading protect decision counters", extra={"project_id": project_id})
            return {"warn_60m": 0, "block_60m": 0, "last": None}

    def _increment_with_ttl(self, key: str) -> None:
        value = self._redis_client.incr(key)
        if value == 1:
            self._redis_client.expire(key, _COUNTER_TTL_SECONDS)

    def _read_int(self, key: str) -> int:
        raw = self._redis_client.get(key)
        if raw is None:
            return 0
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    def _parse_last(self, raw: object) -> dict[str, str] | None:
        if raw is None:
            return None
        value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        decision = str(parsed.get("decision") or "")
        reason = str(parsed.get("reason") or "")
        ts = str(parsed.get("ts") or "")
        if not decision or not reason or not ts:
            return None
        return {"decision": decision, "reason": reason, "ts": ts}
