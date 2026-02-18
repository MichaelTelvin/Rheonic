# Application service for protect mode decision and project protect settings.
from dataclasses import dataclass

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.services.ingest_key_service import IngestKeyService
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ProtectDecision:
    # Decision payload returned by protect preflight endpoint.
    decision: str
    reason: str
    fail_mode: str
    decision_timeout_ms: int
    snapshot: dict[str, int | str | None]


class ProtectService:
    # Handles protect decision evaluation and project-level protect settings.

    def __init__(
        self,
        ingest_key_service: IngestKeyService,
        realtime_counters: RealtimeCounterStore,
        incident_severity_cache: IncidentSeverityCache,
    ) -> None:
        self._ingest_key_service = ingest_key_service
        self._realtime_counters = realtime_counters
        self._incident_severity_cache = incident_severity_cache

    def evaluate_decision(self, ingest_key: str) -> tuple[str | None, ProtectDecision | None]:
        # Resolve project and evaluate protect decision using Redis-backed counters and severity cache.
        project = self._ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            return None, None

        project_id = project.id
        requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=project_id)
        incident_severity = self._incident_severity_cache.get(project_id=project_id)
        max_req = project.protect_max_req_per_min
        max_tok = project.protect_max_tok_per_min
        fail_mode = project.protect_fail_mode
        decision_timeout_ms = project.protect_decision_timeout_ms

        decision = "allow"
        reason = "ok"

        if not project.protect_enabled:
            decision = "allow"
            reason = "ok"
        elif max_req is not None and requests_60s >= max_req:
            decision = "block"
            reason = "req_limit"
        elif max_tok is not None and tokens_60s >= max_tok:
            decision = "block"
            reason = "tok_limit"
        elif incident_severity == "high":
            decision = "block"
            reason = "incident_high"
        elif incident_severity == "medium":
            decision = "warn"
            reason = "incident_medium"

        return project_id, ProtectDecision(
            decision=decision,
            reason=reason,
            fail_mode=fail_mode,
            decision_timeout_ms=decision_timeout_ms,
            snapshot={
                "requests_60s": requests_60s,
                "tokens_60s": tokens_60s,
                "protect_max_req_per_min": max_req,
                "protect_max_tok_per_min": max_tok,
                "incident_severity": incident_severity,
            },
        )
