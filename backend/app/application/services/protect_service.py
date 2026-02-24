# Application service for protect mode decision and project protect settings.
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Callable

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.ingest_key_service import IngestKeyService
from app.config import app_config
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
    retry_after_seconds: int | None
    blocked_until: str | None
    snapshot: dict[str, int | str | bool | None | dict[str, int | bool | None]]


@dataclass(slots=True)
class ProtectDecisionContext:
    # Optional request context used for proactive predictive blocking.
    max_output_tokens: int | None = None
    input_tokens_estimate: int | None = None
    environment: str | None = None
    provider: str | None = None


class ProtectService:
    # Handles protect decision evaluation and project-level protect settings.

    def __init__(
        self,
        ingest_key_service: IngestKeyService,
        realtime_counters: RealtimeCounterStore,
        incident_severity_cache: IncidentSeverityCache,
        protect_action_store: ProtectActionStore,
        protect_block_cooldown_seconds: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._ingest_key_service = ingest_key_service
        self._realtime_counters = realtime_counters
        self._incident_severity_cache = incident_severity_cache
        self._protect_action_store = protect_action_store
        self._protect_block_cooldown_seconds = protect_block_cooldown_seconds
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

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
        scoped_id = scoped_project_provider_id(project_id, ctx.provider)
        now = self._now_provider()
        now_ms = int(now.timestamp() * 1000)
        max_req = project.protect_max_req_per_min
        max_tok = project.protect_max_tok_per_min
        fail_mode = project.protect_fail_mode
        decision_timeout_ms = project.protect_decision_timeout_ms

        if not project.protect_enabled:
            requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)
            incident_severity = self._incident_severity_cache.get(project_id=scoped_id)
            decision = "allow"
            reason = "ok"
            self._protect_action_store.record(project_id=scoped_id, decision=decision, reason=reason)
            return project_id, ProtectDecision(
                decision=decision,
                reason=reason,
                fail_mode=fail_mode,
                decision_timeout_ms=decision_timeout_ms,
                retry_after_seconds=None,
                blocked_until=None,
                snapshot={
                    "requests_60s": requests_60s,
                    "tokens_60s": tokens_60s,
                    "threshold_req_60s": max_req,
                    "threshold_tok_60s": max_tok,
                    "incident_severity": incident_severity,
                    "decision_timeout_ms": decision_timeout_ms,
                    "predictive": {
                        "enabled": False,
                        "estimated_next_tokens": None,
                        "would_exceed_tokens_cap": False,
                    },
                },
            )

        cooldown_until_ms = self._protect_action_store.get_block_cooldown_until_ms(project_id=scoped_id)
        if cooldown_until_ms is not None and now_ms < cooldown_until_ms:
            requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)
            incident_severity = self._incident_severity_cache.get(project_id=scoped_id)
            retry_after_seconds = max(0, ceil((cooldown_until_ms - now_ms) / 1000))
            return project_id, ProtectDecision(
                decision="block",
                reason="cooldown_active",
                fail_mode=fail_mode,
                decision_timeout_ms=decision_timeout_ms,
                retry_after_seconds=retry_after_seconds,
                blocked_until=datetime.fromtimestamp(cooldown_until_ms / 1000, tz=timezone.utc).isoformat(),
                snapshot={
                    "requests_60s": requests_60s,
                    "tokens_60s": tokens_60s,
                    "threshold_req_60s": max_req,
                    "threshold_tok_60s": max_tok,
                    "incident_severity": incident_severity,
                    "decision_timeout_ms": decision_timeout_ms,
                    "predictive": {
                        "enabled": False,
                        "estimated_next_tokens": None,
                        "would_exceed_tokens_cap": False,
                    },
                },
            )

        requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)
        incident_severity = self._incident_severity_cache.get(project_id=scoped_id)
        near_cap_threshold = float(max_tok) * app_config.protect_near_cap_factor if max_tok is not None else None
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

        req_cap_exceeded = bool(max_req is not None and requests_60s >= max_req)
        tok_cap_exceeded = bool(max_tok is not None and tokens_60s >= max_tok)
        incident_high = incident_severity == "high"
        incident_medium = incident_severity == "medium"
        predictive_near_cap = near_cap_reached

        decision = "allow"
        reason = "ok"
        retry_after_seconds: int | None = None
        blocked_until: str | None = None

        if tok_cap_exceeded:
            decision = "block"
            reason = "tok_limit"
        elif req_cap_exceeded:
            decision = "block"
            reason = "req_limit"
        elif incident_high:
            decision = "block"
            reason = "incident_high"
        elif incident_medium:
            decision = "warn"
            reason = "incident_medium"
        elif predictive_near_cap:
            decision = "warn"
            reason = "predictive_near_cap"

        if decision == "block" and reason in {"req_limit", "tok_limit", "incident_high"}:
            cooldown_seconds = max(int(self._protect_block_cooldown_seconds), 1)
            blocked_until_ms = now_ms + (cooldown_seconds * 1000)
            blocked_until = datetime.fromtimestamp(blocked_until_ms / 1000, tz=timezone.utc).isoformat()
            retry_after_seconds = max(0, ceil((blocked_until_ms - now_ms) / 1000))
            self._protect_action_store.set_block_cooldown(
                project_id=scoped_id,
                blocked_until_ms=blocked_until_ms,
                cooldown_seconds=cooldown_seconds,
            )

        self._protect_action_store.record(project_id=scoped_id, decision=decision, reason=reason)

        return project_id, ProtectDecision(
            decision=decision,
            reason=reason,
            fail_mode=fail_mode,
            decision_timeout_ms=decision_timeout_ms,
            retry_after_seconds=retry_after_seconds,
            blocked_until=blocked_until,
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
