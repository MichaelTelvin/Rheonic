# Rolling window helper scaffolding.
import time
from collections.abc import Callable
from statistics import median
from typing import Protocol
from uuid import uuid4

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.config import app_config
from app.logger import get_logger

logger = get_logger(__name__)


def requests_60s_key(project_id: str) -> str:
    # Return the Redis key for request ZSET in the 60s window.
    return f"rt:{project_id}:req:z"


def tokens_60s_key(project_id: str) -> str:
    # Return the Redis key for token ZSET in the 60s window.
    return f"rt:{project_id}:tok:z"


def incident_open_lock_key(project_id: str, incident_type: str) -> str:
    # Return the redis lock key used to dedupe incidents.
    return f"inc:{project_id}:{incident_type}:open"


def baseline_req_60s_key(project_id: str) -> str:
    # Return the Redis key for request baseline list.
    return f"bl:{project_id}:req"


def baseline_tok_60s_key(project_id: str) -> str:
    # Return the Redis key for token baseline list.
    return f"bl:{project_id}:tok"


def normalize_total_tokens(total_tokens: int | None) -> int:
    # Normalize token values, defaulting missing values to zero.
    if total_tokens is None:
        return 0
    return total_tokens


class RedisCounterClient(Protocol):
    # Protocol for minimal Redis counter commands used by this adapter.

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        # Add a scored member to a sorted set.
        ...

    def zremrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> int:
        # Remove members in score range.
        ...

    def zcard(self, key: str) -> int:
        # Return sorted set cardinality.
        ...

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        # Return sorted set members in score range.
        ...

    def lpush(self, key: str, value: object) -> int:
        # Push value to the list head.
        ...

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        # Trim list to start..stop range.
        ...

    def lrange(self, key: str, start: int, stop: int) -> list[object]:
        # Return list values for start..stop range.
        ...

    def expire(self, key: str, ttl_seconds: int) -> bool:
        # Set expiration for a key.
        ...

    def get(self, key: str) -> object | None:
        # Read a key value.
        ...

    def set_nx_ex(self, key: str, value: object, ttl_seconds: int) -> bool:
        # Set key with NX and expiration semantics.
        ...

    def delete(self, key: str) -> int:
        # Delete a key.
        ...


class RollingWindow(RealtimeCounterStore):
    # Tracks time-windowed counters for anomaly detection and limits.

    def __init__(
        self,
        client: RedisCounterClient,
        now_ms_provider: Callable[[], int] | None = None,
        member_id_provider: Callable[[], str] | None = None,
    ) -> None:
        # Initialize rolling-window adapter.
        self._client = client
        self._now_ms_provider = now_ms_provider or _default_now_ms
        self._member_id_provider = member_id_provider or _default_member_id

    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        # Add request/token points to rolling ZSETs and trim older-than-60s data.
        try:
            req_key = requests_60s_key(project_id)
            tok_key = tokens_60s_key(project_id)
            normalized_tokens = normalize_total_tokens(total_tokens)
            now_ms = self._now_ms_provider()
            cutoff_ms = now_ms - app_config.rolling_window_ms
            member_id = self._member_id_provider()
            req_member = f"{now_ms}:{member_id}:1"
            tok_member = f"{now_ms}:{member_id}:{normalized_tokens}"

            self._client.zadd(req_key, {req_member: now_ms})
            self._client.zremrangebyscore(req_key, 0, cutoff_ms)
            self._client.expire(req_key, app_config.rolling_counter_ttl_seconds)

            self._client.zadd(tok_key, {tok_member: now_ms})
            self._client.zremrangebyscore(tok_key, 0, cutoff_ms)
            self._client.expire(tok_key, app_config.rolling_counter_ttl_seconds)

            logger.debug("Realtime counters incremented", extra={"project_id": project_id})
        except Exception:
            logger.exception("Failed incrementing realtime counters", extra={"project_id": project_id})
            raise

    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        # Return request and token rolling-window aggregates for the last 60s.
        try:
            req_key = requests_60s_key(project_id)
            tok_key = tokens_60s_key(project_id)
            now_ms = self._now_ms_provider()
            cutoff_ms = now_ms - app_config.rolling_window_ms

            self._client.zremrangebyscore(req_key, 0, cutoff_ms)
            self._client.zremrangebyscore(tok_key, 0, cutoff_ms)

            requests_60s = self._client.zcard(req_key)
            token_members = self._client.zrangebyscore(tok_key, cutoff_ms, float("inf"))
            tokens_60s = sum(_member_tokens(member) for member in token_members)
            counters = requests_60s, tokens_60s
            logger.debug("Realtime counters fetched", extra={"project_id": project_id})
            return counters
        except Exception:
            logger.exception("Failed fetching realtime counters", extra={"project_id": project_id})
            raise

    def record_baseline_snapshot(
        self,
        project_id: str,
        requests_60s: int,
        tokens_60s: int,
        max_windows: int,
    ) -> tuple[float, float]:
        # Record rolling baseline samples and return request/token medians.
        try:
            req_key = baseline_req_60s_key(project_id)
            tok_key = baseline_tok_60s_key(project_id)

            self._client.lpush(req_key, str(requests_60s))
            self._client.ltrim(req_key, 0, max_windows - 1)
            self._client.expire(req_key, app_config.baseline_counter_ttl_seconds)

            self._client.lpush(tok_key, str(tokens_60s))
            self._client.ltrim(tok_key, 0, max_windows - 1)
            self._client.expire(tok_key, app_config.baseline_counter_ttl_seconds)

            req_values = [_coerce_int(value) for value in self._client.lrange(req_key, 0, max_windows - 1)]
            tok_values = [_coerce_int(value) for value in self._client.lrange(tok_key, 0, max_windows - 1)]
            return median_or_zero(req_values), median_or_zero(tok_values)
        except Exception:
            logger.exception("Failed recording baseline snapshot", extra={"project_id": project_id})
            raise

    def acquire_incident_lock(self, project_id: str, incident_type: str, ttl_seconds: int) -> bool:
        # Acquire incident dedupe lock.
        try:
            key = incident_open_lock_key(project_id, incident_type)
            acquired = self._client.set_nx_ex(key, "1", ttl_seconds)
            logger.debug(
                "Incident dedupe lock attempt",
                extra={"project_id": project_id, "incident_type": incident_type, "acquired": acquired},
            )
            return acquired
        except Exception:
            logger.exception("Failed acquiring incident lock", extra={"project_id": project_id, "incident_type": incident_type})
            raise

    def release_incident_lock(self, project_id: str, incident_type: str) -> None:
        # Release incident dedupe lock.
        try:
            key = incident_open_lock_key(project_id, incident_type)
            self._client.delete(key)
            logger.debug("Incident dedupe lock released", extra={"project_id": project_id, "incident_type": incident_type})
        except Exception:
            logger.exception("Failed releasing incident lock", extra={"project_id": project_id, "incident_type": incident_type})
            raise


def _member_tokens(member: object) -> int:
    # Parse tokens from member format "{now_ms}:{uuid}:{tokens}".
    if isinstance(member, bytes):
        member = member.decode("utf-8")
    parts = str(member).split(":")
    return int(parts[-1]) if parts else 0


def _coerce_int(value: object) -> int:
    # Parse integer values from redis list payloads.
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return int(value)


def median_or_zero(values: list[int]) -> float:
    # Return list median or zero when no values are available.
    if not values:
        return 0.0
    return float(median(values))


def _default_now_ms() -> int:
    # Return current unix time in milliseconds.
    return int(time.time() * 1000)


def _default_member_id() -> str:
    # Return unique member identifier component.
    return uuid4().hex
