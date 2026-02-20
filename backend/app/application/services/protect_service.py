# Application service for protect mode decision and project protect settings.
from dataclasses import dataclass

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.services.ingest_key_service import IngestKeyService
from app.infrastructure.redis.incident_severity_cache import IncidentSeverityCache
from app.infrastructure.redis.protect_action_store import ProtectActionStore
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ProtectDecision:
    # Decision payload returned by protect preflight endpoint.
    decision: str
    reason: str
    fail_mode: str
    decision_timeout_ms: int
    snapshot: dict[str, int | str | bool | None | dict[str, int | bool | None]]


@dataclass(slots=True)
class ProtectDecisionContext:
    # Optional request context used for proactive predictive blocking.
    max_output_tokens: int | None = None
    input_tokens_estimate: int | None = None
    environment: str | None = None


class ProtectService:
    # Handles protect decision evaluation and project-level protect settings.

    def __init__(
        self,
        ingest_key_service: IngestKeyService,
        realtime_counters: RealtimeCounterStore,
        incident_severity_cache: IncidentSeverityCache,
        protect_action_store: ProtectActionStore,
    ) -> None:
        self._ingest_key_service = ingest_key_service
        self._realtime_counters = realtime_counters
        self._incident_severity_cache = incident_severity_cache
        self._protect_action_store = protect_action_store

    def evaluate_decision(
        self,
        ingest_key: str,
        context: ProtectDecisionContext | None = None,
    ) -> tuple[str | None, ProtectDecision | None]:
        # Resolve project and evaluate protect decision using Redis-backed counters and severity cache.
        project = self._ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            return None, None

        ctx = context or ProtectDecisionContext()
        project_id = project.id
        requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=project_id)
        incident_severity = self._incident_severity_cache.get(project_id=project_id)
        max_req = project.protect_max_req_per_min
        max_tok = project.protect_max_tok_per_min
        fail_mode = project.protect_fail_mode
        decision_timeout_ms = project.protect_decision_timeout_ms
        near_cap_threshold = float(max_tok) * 0.8 if max_tok is not None else None
        estimated_next_tokens: int | None = None
        if isinstance(ctx.input_tokens_estimate, int):
            input_estimate = max(ctx.input_tokens_estimate, 0)
            if isinstance(ctx.max_output_tokens, int):
                estimated_next_tokens = input_estimate + max(ctx.max_output_tokens, 0)
            else:
                estimated_next_tokens = input_estimate

        predictive_enabled = bool(project.protect_enabled and max_tok is not None and estimated_next_tokens is not None)
        near_cap_reached = bool(
            near_cap_threshold is not None
            and estimated_next_tokens is not None
            and (tokens_60s + estimated_next_tokens >= near_cap_threshold)
        )
        would_exceed_tokens_cap = bool(
            max_tok is not None and estimated_next_tokens is not None and (tokens_60s + estimated_next_tokens >= max_tok)
        )

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
        elif near_cap_reached:
            decision = "warn"
            reason = "predictive_near_cap"

        self._protect_action_store.record(project_id=project_id, decision=decision, reason=reason)

        return project_id, ProtectDecision(
            decision=decision,
            reason=reason,
            fail_mode=fail_mode,
            decision_timeout_ms=decision_timeout_ms,
            snapshot={
                "requests_60s": requests_60s,
                "tokens_60s": tokens_60s,
                "threshold_req_60s": max_req,
                "threshold_tok_60s": max_tok,
                "incident_severity": incident_severity,
                "decision_timeout_ms": decision_timeout_ms,
                "predictive": {
                    "enabled": predictive_enabled,
                    "estimated_next_tokens": estimated_next_tokens,
                    "would_exceed_tokens_cap": would_exceed_tokens_cap,
                },
            },
        )
