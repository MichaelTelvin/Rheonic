# Redis-backed cache for latest open incident severity by project.
from app.infrastructure.redis.redis_client import RedisClient
from app.logger import get_logger

logger = get_logger(__name__)


def incident_severity_key(project_id: str) -> str:
    # Return cache key for latest project incident severity.
    return f"incsev:{project_id}"


class IncidentSeverityCache:
    # Thin adapter for incident severity cache operations.

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    def get(self, project_id: str) -> str:
        # Return cached severity, defaulting to none.
        try:
            raw_value = self._redis_client.get(incident_severity_key(project_id))
            if raw_value is None:
                return "none"
            if isinstance(raw_value, bytes):
                return raw_value.decode("utf-8")
            return str(raw_value)
        except Exception:
            logger.warning("Failed reading incident severity cache", extra={"project_id": project_id})
            return "none"

    def set(self, project_id: str, severity: str) -> None:
        # Persist latest severity value without TTL.
        try:
            self._redis_client.set_persistent(incident_severity_key(project_id), severity)
        except Exception:
            logger.warning(
                "Failed updating incident severity cache",
                extra={"project_id": project_id, "severity": severity},
            )
