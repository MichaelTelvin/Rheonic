# Rolling window helper scaffolding.
from typing import Protocol

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.logger import get_logger

logger = get_logger(__name__)
WINDOW_SECONDS = 60
COUNTER_TTL_SECONDS = 120


def requests_60s_key(project_id: str) -> str:
    # Return the Redis key for request count in the 60s window.
    return f"rt:{project_id}:req:60s"


def tokens_60s_key(project_id: str) -> str:
    # Return the Redis key for token count in the 60s window.
    return f"rt:{project_id}:tok:60s"


def incident_open_lock_key(project_id: str, incident_type: str) -> str:
    # Return the redis lock key used to dedupe incidents.
    return f"inc:{project_id}:{incident_type}:open"


def normalize_total_tokens(total_tokens: int | None) -> int:
    # Normalize token values, defaulting missing values to zero.
    if total_tokens is None:
        return 0
    return total_tokens


class RedisCounterClient(Protocol):
    # Protocol for minimal Redis counter commands used by this adapter.

    def incr(self, key: str) -> int:
        # Increment a key by one.
        ...

    def incrby(self, key: str, amount: int) -> int:
        # Increment a key by the provided amount.
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

    def __init__(self, client: RedisCounterClient) -> None:
        # Initialize rolling-window adapter.
        self._client = client

    def increment_project_60s(self, project_id: str, total_tokens: int) -> None:
        # Increment request/token counters and refresh TTL for project keys.
        try:
            req_key = requests_60s_key(project_id)
            tok_key = tokens_60s_key(project_id)
            normalized_tokens = normalize_total_tokens(total_tokens)

            self._client.incr(req_key)
            self._client.expire(req_key, COUNTER_TTL_SECONDS)
            self._client.incrby(tok_key, normalized_tokens)
            self._client.expire(tok_key, COUNTER_TTL_SECONDS)
            logger.debug("Realtime counters incremented", extra={"project_id": project_id})
        except Exception:
            logger.exception("Failed incrementing realtime counters", extra={"project_id": project_id})
            raise

    def get_project_60s(self, project_id: str) -> tuple[int, int]:
        # Return request and token counters for the last 60s project window.
        try:
            req_key = requests_60s_key(project_id)
            tok_key = tokens_60s_key(project_id)
            request_value = self._client.get(req_key)
            token_value = self._client.get(tok_key)
            counters = _coerce_redis_int(request_value), _coerce_redis_int(token_value)
            logger.debug("Realtime counters fetched", extra={"project_id": project_id})
            return counters
        except Exception:
            logger.exception("Failed fetching realtime counters", extra={"project_id": project_id})
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


def _coerce_redis_int(value: object | None) -> int:
    # Convert Redis values to integers with a zero fallback.
    if value is None:
        return 0
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return int(value)
