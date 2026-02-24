# Application service for metrics aggregation.
from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.project_repository import ProjectRepository
from app.application.provider_scope import scoped_project_provider_id
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.logger import get_logger

logger = get_logger(__name__)


class MetricsService:
    # Builds incident-first dashboard metrics.

    def __init__(
        self,
        realtime_counters: RealtimeCounterStore,
        protect_action_store: ProtectActionStore,
        project_repository: ProjectRepository,
    ) -> None:
        # Initialize service dependencies.
        self._realtime_counters = realtime_counters
        self._protect_action_store = protect_action_store
        self._project_repository = project_repository

    def get_realtime(self, project_id: str, provider: str | None = None) -> dict[str, int]:
        # Return realtime request/token counters aggregated across project providers.
        try:
            requests_60s = 0
            tokens_60s = 0
            for scoped_provider in self._project_providers_for_aggregation(project_id=project_id, provider=provider):
                provider_requests, provider_tokens = self._realtime_counters.get_project_60s(
                    scoped_project_provider_id(project_id, scoped_provider),
                )
                requests_60s += provider_requests
                tokens_60s += provider_tokens
            logger.debug("Realtime counters read", extra={"project_id": project_id})
            return {
                "requests_60s": requests_60s,
                "tokens_60s": tokens_60s,
            }
        except Exception:
            logger.exception("Metrics service failed", extra={"project_id": project_id})
            raise

    def get_protect_metrics(self, project_id: str, provider: str | None = None) -> dict[str, object]:
        # Return normalized protect counters and latency metrics aggregated across providers.
        try:
            totals: dict[str, int] = {
                "allowed_60m": 0,
                "warned_60m": 0,
                "blocked_60m": 0,
                "decision_timeouts_60m": 0,
            }
            latencies_p50: list[int] = []
            latencies_p95: list[int] = []
            latest_last: dict[str, str] | None = None
            latest_last_ts = ""
            for scoped_provider in self._project_providers_for_aggregation(project_id=project_id, provider=provider):
                raw = self._protect_action_store.get_metrics(project_id=scoped_project_provider_id(project_id, scoped_provider))
                totals["allowed_60m"] += int(raw.get("allowed_60m", 0) or 0)
                totals["warned_60m"] += int(raw.get("warned_60m", 0) or 0)
                totals["blocked_60m"] += int(raw.get("blocked_60m", 0) or 0)
                totals["decision_timeouts_60m"] += int(raw.get("decision_timeouts_60m", 0) or 0)
                if isinstance(raw.get("decision_latency_p50_60m_ms"), int):
                    latencies_p50.append(int(raw["decision_latency_p50_60m_ms"]))
                if isinstance(raw.get("decision_latency_p95_60m_ms"), int):
                    latencies_p95.append(int(raw["decision_latency_p95_60m_ms"]))
                raw_last = raw.get("last")
                if isinstance(raw_last, dict):
                    ts = str(raw_last.get("ts") or "")
                    if ts and ts >= latest_last_ts:
                        latest_last_ts = ts
                        latest_last = raw_last
            metrics = {
                "allowed_60m": totals["allowed_60m"],
                "warned_60m": totals["warned_60m"],
                "blocked_60m": totals["blocked_60m"],
                "decision_timeouts_60m": totals["decision_timeouts_60m"],
                "decision_latency_p50_60m_ms": (round(sum(latencies_p50) / len(latencies_p50)) if latencies_p50 else None),
                "decision_latency_p95_60m_ms": (round(sum(latencies_p95) / len(latencies_p95)) if latencies_p95 else None),
                "last": latest_last,
            }
            logger.debug("Protect metrics read", extra={"project_id": project_id})
            return metrics
        except Exception:
            logger.exception("Protect metrics service failed", extra={"project_id": project_id})
            raise

    def get_protect_health(self, project_id: str, provider: str | None = None) -> dict[str, object]:
        # Return protect preflight health metrics aggregated across providers.
        try:
            p50_values: list[int] = []
            p95_values: list[int] = []
            timeouts_60m = 0
            for scoped_provider in self._project_providers_for_aggregation(project_id=project_id, provider=provider):
                metrics = self._protect_action_store.get_health(project_id=scoped_project_provider_id(project_id, scoped_provider))
                if isinstance(metrics.get("p50_ms"), int):
                    p50_values.append(int(metrics["p50_ms"]))
                if isinstance(metrics.get("p95_ms"), int):
                    p95_values.append(int(metrics["p95_ms"]))
                timeouts_60m += int(metrics.get("timeouts_60m", 0) or 0)
            metrics = {
                "p50_ms": (round(sum(p50_values) / len(p50_values)) if p50_values else None),
                "p95_ms": (round(sum(p95_values) / len(p95_values)) if p95_values else None),
                "timeouts_60m": timeouts_60m,
            }
            logger.debug("Protect health read", extra={"project_id": project_id})
            return metrics
        except Exception:
            logger.exception("Protect health service failed", extra={"project_id": project_id})
            raise

    def _project_providers_for_aggregation(self, project_id: str, provider: str | None = None) -> list[str]:
        # Return providers to sum for project-level dashboard metrics or one selected provider.
        if provider:
            return [provider]
        providers = self._project_repository.list_project_providers(project_id=project_id)
        if providers:
            return providers
        # Fallback keeps protect counters visible for projects with preflight traffic before first ingest event.
        return ["openai", "anthropic", "google", "unknown"]
