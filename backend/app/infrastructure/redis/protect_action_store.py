# Redis-backed protect decision audit counters for dashboard visibility.
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import app_config
from app.infrastructure.redis.redis_client import RedisClient
from app.logger import get_logger

logger = get_logger(__name__)


def _warn_key(project_id: str) -> str:
    return f"pa:{project_id}:warn:60m"


def _block_key(project_id: str) -> str:
    return f"pa:{project_id}:block:60m"


def _allow_key(project_id: str) -> str:
    return f"pa:{project_id}:allow:60m"


def _last_key(project_id: str) -> str:
    return f"pa:{project_id}:last"


def _latency_key(project_id: str) -> str:
    return f"pa:{project_id}:latency:60m"


def _timeout_key(project_id: str) -> str:
    return f"pa:{project_id}:timeout:60m"


def _request_key(project_id: str, request_id: str) -> str:
    return f"pa:{project_id}:request:{request_id}"


def _timed_out_request_key(project_id: str, request_id: str) -> str:
    return f"pa:{project_id}:timedout:{request_id}"


class ProtectActionStore:
    # Stores protect decision counters and last decision snapshot in Redis.

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    def record(self, project_id: str, decision: str, reason: str, request_id: str | None = None, ts: datetime | None = None) -> None:
        # Record warn/block counters and keep the last decision payload for UI.
        timestamp = (ts or datetime.now(timezone.utc)).isoformat()
        try:
            if request_id and self._redis_client.get(_timed_out_request_key(project_id, request_id)) is not None:
                return
            if decision == "allow":
                self._increment_with_ttl(_allow_key(project_id))
            elif decision == "warn":
                self._increment_with_ttl(_warn_key(project_id))
            elif decision == "block":
                self._increment_with_ttl(_block_key(project_id))

            payload = {"decision": decision, "reason": reason, "ts": timestamp}
            self._redis_client.set(_last_key(project_id), json.dumps(payload), ex=app_config.protect_action_counter_ttl_seconds)
            if request_id:
                self._redis_client.set(
                    _request_key(project_id, request_id),
                    json.dumps(payload),
                    ex=app_config.protect_action_counter_ttl_seconds,
                )
        except Exception:
            logger.warning("Failed recording protect decision counters", extra={"project_id": project_id})

    def get_metrics(self, project_id: str) -> dict[str, Any]:
        # Read 60-minute protect decision counters and last decision snapshot.
        try:
            allowed = self._read_int(_allow_key(project_id))
            warn = self._read_int(_warn_key(project_id))
            block = self._read_int(_block_key(project_id))
            decision_timeouts = self._read_int(_timeout_key(project_id))
            last_raw = self._redis_client.get(_last_key(project_id))
            health = self.get_health(project_id=project_id)
            return {
                "allowed_60m": allowed,
                "warned_60m": warn,
                "blocked_60m": block,
                "decision_timeouts_60m": decision_timeouts,
                "last": self._parse_last(last_raw),
                "decision_latency_p50_60m_ms": health.get("p50_ms"),
                "decision_latency_p95_60m_ms": health.get("p95_ms"),
            }
        except Exception:
            logger.warning("Failed reading protect decision counters", extra={"project_id": project_id})
            return {
                "allowed_60m": 0,
                "warned_60m": 0,
                "blocked_60m": 0,
                "decision_timeouts_60m": 0,
                "last": None,
                "decision_latency_p50_60m_ms": None,
                "decision_latency_p95_60m_ms": None,
            }

    def record_decision_timeout(
        self,
        project_id: str,
        request_id: str | None = None,
        effective_decision: str = "allow",
    ) -> None:
        # Record one SDK-reported decision-timeout in the 60-minute counter.
        try:
            if effective_decision == "block":
                self._increment_with_ttl(_block_key(project_id))
            else:
                self._increment_with_ttl(_allow_key(project_id))
            self._increment_with_ttl(_timeout_key(project_id))
            now = datetime.now(timezone.utc).isoformat()
            self._redis_client.set(
                _last_key(project_id),
                json.dumps({"decision": "block" if effective_decision == "block" else "allow", "reason": "decision_timeout", "ts": now}),
                ex=app_config.protect_action_counter_ttl_seconds,
            )
            if request_id:
                self._redis_client.set(
                    _timed_out_request_key(project_id, request_id),
                    "1",
                    ex=app_config.protect_action_counter_ttl_seconds,
                )
                request_raw = self._redis_client.get(_request_key(project_id, request_id))
                request_payload = self._parse_last(request_raw)
                if request_payload is not None:
                    self._decrement_counter_for_decision(project_id=project_id, decision=request_payload["decision"])
                self._redis_client.delete(_request_key(project_id, request_id))
        except Exception:
            logger.warning("Failed recording protect decision timeout", extra={"project_id": project_id})

    def record_health(self, project_id: str, latency_ms: int, timed_out: bool = False, ts: datetime | None = None) -> None:
        # Record preflight latency samples and timeout counters over a 60-minute window.
        try:
            now_ms = int((ts or datetime.now(timezone.utc)).timestamp() * 1000)
            cutoff_ms = now_ms - (app_config.protect_action_counter_ttl_seconds * 1000)
            normalized_latency = max(int(latency_ms), 0)
            member = f"{now_ms}:{uuid4().hex[:8]}:{normalized_latency}"
            latency_key = _latency_key(project_id)
            self._redis_client.zadd(latency_key, {member: now_ms})
            self._redis_client.zremrangebyscore(latency_key, 0, cutoff_ms)
            self._redis_client.expire(latency_key, app_config.protect_action_counter_ttl_seconds)
            if timed_out:
                self._increment_with_ttl(_timeout_key(project_id))
        except Exception:
            logger.warning("Failed recording protect health counters", extra={"project_id": project_id})

    def set_block_cooldown(self, project_id: str, blocked_until_ms: int, cooldown_seconds: int) -> None:
        # Persist project-level protect cooldown window in Redis.
        try:
            self._redis_client.set(f"protect:cooldown:{project_id}", str(int(blocked_until_ms)), ex=max(int(cooldown_seconds), 1))
        except Exception:
            logger.warning("Failed setting protect cooldown", extra={"project_id": project_id})

    def get_block_cooldown_until_ms(self, project_id: str) -> int | None:
        # Read active project-level protect cooldown expiry in epoch milliseconds.
        try:
            raw = self._redis_client.get(f"protect:cooldown:{project_id}")
            if raw is None:
                return None
            value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            parsed = int(value)
            return parsed if parsed > 0 else None
        except Exception:
            logger.warning("Failed reading protect cooldown", extra={"project_id": project_id})
            return None

    def get_health(self, project_id: str) -> dict[str, Any]:
        # Read 60-minute preflight latency percentiles and timeout counter.
        try:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            cutoff_ms = now_ms - (app_config.protect_action_counter_ttl_seconds * 1000)
            latency_key = _latency_key(project_id)
            self._redis_client.zremrangebyscore(latency_key, 0, cutoff_ms)
            latency_members = self._redis_client.zrangebyscore(latency_key, cutoff_ms, float("inf"))
            latencies = self._parse_latencies(latency_members)
            return {
                "p50_ms": self._percentile(latencies, 50),
                "p95_ms": self._percentile(latencies, 95),
                "timeouts_60m": self._read_int(_timeout_key(project_id)),
            }
        except Exception:
            logger.warning("Failed reading protect health counters", extra={"project_id": project_id})
            return {"p50_ms": None, "p95_ms": None, "timeouts_60m": 0}

    def _increment_with_ttl(self, key: str) -> None:
        value = self._redis_client.incr(key)
        if value == 1:
            self._redis_client.expire(key, app_config.protect_action_counter_ttl_seconds)

    def _decrement_counter_for_decision(self, *, project_id: str, decision: str) -> None:
        key = (
            _allow_key(project_id)
            if decision == "allow"
            else _warn_key(project_id)
            if decision == "warn"
            else _block_key(project_id)
            if decision == "block"
            else None
        )
        if key is None:
            return
        current = self._read_int(key)
        if current <= 0:
            return
        self._redis_client.incrby(key, -1)

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

    def _parse_latencies(self, members: list[object]) -> list[int]:
        values: list[int] = []
        for raw_member in members:
            member = raw_member.decode("utf-8") if isinstance(raw_member, bytes) else str(raw_member)
            parts = member.rsplit(":", 1)
            if len(parts) != 2:
                continue
            try:
                values.append(max(int(parts[1]), 0))
            except (TypeError, ValueError):
                continue
        values.sort()
        return values

    def _percentile(self, values: list[int], percentile: int) -> int | None:
        if not values:
            return None
        rank = math.ceil((percentile / 100) * len(values)) - 1
        index = min(max(rank, 0), len(values) - 1)
        return values[index]
