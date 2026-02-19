# Application service for metrics aggregation.
from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.logger import get_logger

logger = get_logger(__name__)


class MetricsService:
    # Builds incident-first dashboard metrics.

    def __init__(
        self,
        realtime_counters: RealtimeCounterStore,
        protect_action_store: ProtectActionStore,
    ) -> None:
        # Initialize service dependencies.
        self._realtime_counters = realtime_counters
        self._protect_action_store = protect_action_store

    def get_realtime(self, project_id: str) -> dict[str, int]:
        # Return realtime request/token counters for the project.
        try:
            # retrieve counters from Redis adapter
            requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id)
            logger.debug("Realtime counters read", extra={"project_id": project_id})
            return {
                "requests_60s": requests_60s,
                "tokens_60s": tokens_60s,
            }
        except Exception:
            logger.exception("Metrics service failed", extra={"project_id": project_id})
            raise

    def get_protect_metrics(self, project_id: str) -> dict[str, object]:
        # Return protect action counters for the project.
        try:
            metrics = self._protect_action_store.get_metrics(project_id=project_id)
            logger.debug("Protect metrics read", extra={"project_id": project_id})
            return metrics
        except Exception:
            logger.exception("Protect metrics service failed", extra={"project_id": project_id})
            raise
