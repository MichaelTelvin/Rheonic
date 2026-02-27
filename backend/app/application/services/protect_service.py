# Application service for protect mode decision and project protect settings.
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Callable

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.ingest_key_service import IngestKeyService
from app.config import app_config
from app.domain.detectors.contracts import DetectionContext
from app.domain.detectors.loop_suspect_detector import LoopSuspectDetector
from app.domain.detectors.near_cap_detector import NearCapDetector
from app.domain.detectors.registry import DetectorRegistry
from app.domain.detectors.retry_storm_detector import RetryStormDetector
from app.domain.detectors.token_explosion_detector import TokenExplosionDetector
from app.infrastructure.redis.protect_action_store import ProtectActionStore


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
    # Optional request context used for proactive predictive warning.
    max_output_tokens: int | None = None
    input_tokens_estimate: int | None = None
    environment: str | None = None
    provider: str | None = None
    model: str | None = None


class ProtectService:
    # Handles protect decision evaluation and project-level protect settings.

    def __init__(
        self,
        ingest_key_service: IngestKeyService,
        realtime_counters: RealtimeCounterStore,
        protect_action_store: ProtectActionStore,
        protect_block_cooldown_seconds: int,
        event_repository: EventRepository | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._ingest_key_service = ingest_key_service
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._protect_action_store = protect_action_store
        self._protect_block_cooldown_seconds = protect_block_cooldown_seconds
        self._webhook_dispatcher = webhook_dispatcher
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._warn_detector_registry = DetectorRegistry(
            detectors=[
                NearCapDetector(),
                RetryStormDetector(),
                LoopSuspectDetector(),
                TokenExplosionDetector(),
            ]
        )

    def evaluate_decision(
        self,
        ingest_key: str,
        context: ProtectDecisionContext | None = None,
    ) -> tuple[str | None, ProtectDecision | None]:
        project = self._ingest_key_service.resolve_project(plaintext_key=ingest_key)
        if project is None:
            return None, None

        ctx = context or ProtectDecisionContext()
        provider = (ctx.provider or "").strip() or "unknown"
        project_id = project.id
        scoped_id = scoped_project_provider_id(project_id, provider)
        now = self._now_provider()
        now_ms = int(now.timestamp() * 1000)
        max_req = project.protect_max_req_per_min
        max_tok = project.protect_max_tok_per_min
        fail_mode = project.protect_fail_mode
        decision_timeout_ms = project.protect_decision_timeout_ms
        requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)

        if not project.protect_enabled:
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
                    "decision_timeout_ms": decision_timeout_ms,
                    "predictive": {
                        "enabled": False,
                        "estimated_next_tokens": None,
                        "would_exceed_tokens_cap": False,
                    },
                },
            )

        # Caps-first block path.
        if max_tok is not None and tokens_60s >= max_tok:
            return project_id, self._build_block_decision(
                project_id=project_id,
                provider=provider,
                scoped_id=scoped_id,
                reason="tok_cap_breach",
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                fail_mode=fail_mode,
                decision_timeout_ms=decision_timeout_ms,
                now_ms=now_ms,
            )
        if max_req is not None and requests_60s >= max_req:
            return project_id, self._build_block_decision(
                project_id=project_id,
                provider=provider,
                scoped_id=scoped_id,
                reason="req_cap_breach",
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                fail_mode=fail_mode,
                decision_timeout_ms=decision_timeout_ms,
                now_ms=now_ms,
            )

        estimated_next_tokens: int | None = None
        if isinstance(ctx.input_tokens_estimate, int):
            input_estimate = max(ctx.input_tokens_estimate, 0)
            output_estimate = max(ctx.max_output_tokens, 0) if isinstance(ctx.max_output_tokens, int) else 0
            estimated_next_tokens = input_estimate + output_estimate
        recent_events = self._event_repository.list_recent(project_id=project_id, limit=200) if self._event_repository is not None else []
        detector_ctx = DetectionContext(
            project_id=project_id,
            provider=provider,
            model=ctx.model,
            environment=ctx.environment,
            now=now,
            current_requests_60s=requests_60s,
            current_tokens_60s=tokens_60s,
            req_cap=max_req,
            tok_cap=max_tok,
            protect_enabled=True,
            estimated_next_tokens=estimated_next_tokens,
            current_event=None,
            recent_events=recent_events,
            warn_ratio=app_config.protect_near_cap_factor,
            retry_storm_window_seconds=app_config.retry_storm_window_seconds,
            retry_storm_count=app_config.retry_storm_count,
            loop_window_seconds=app_config.loop_window_seconds,
            loop_count=app_config.loop_count,
            token_explosion_ratio=app_config.token_explosion_ratio,
            token_explosion_abs=app_config.token_explosion_abs,
        )
        warn_signals = self._warn_detector_registry.detect(detector_ctx)
        if warn_signals:
            warn_signal = warn_signals[0]
            reason = str(warn_signal.detector)
            self._protect_action_store.record(project_id=scoped_id, decision="warn", reason=reason)
            self._enqueue_warn_webhook(
                project_id=project_id,
                provider=provider,
                reason=reason,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                estimated_next_tokens=estimated_next_tokens,
            )
            return project_id, ProtectDecision(
                decision="warn",
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
                    "decision_timeout_ms": decision_timeout_ms,
                    "predictive": {
                        "enabled": bool(estimated_next_tokens is not None),
                        "estimated_next_tokens": estimated_next_tokens,
                        "would_exceed_tokens_cap": bool(
                            max_tok is not None
                            and estimated_next_tokens is not None
                            and (tokens_60s + estimated_next_tokens >= max_tok)
                        ),
                    },
                },
            )

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
                "decision_timeout_ms": decision_timeout_ms,
                "predictive": {
                    "enabled": bool(estimated_next_tokens is not None),
                    "estimated_next_tokens": estimated_next_tokens,
                    "would_exceed_tokens_cap": bool(
                        max_tok is not None and estimated_next_tokens is not None and (tokens_60s + estimated_next_tokens >= max_tok)
                    ),
                },
            },
        )

    def _build_block_decision(
        self,
        *,
        project_id: str,
        provider: str,
        scoped_id: str,
        reason: str,
        requests_60s: int,
        tokens_60s: int,
        max_req: int | None,
        max_tok: int | None,
        fail_mode: str,
        decision_timeout_ms: int,
        now_ms: int,
    ) -> ProtectDecision:
        cooldown_seconds = max(int(self._protect_block_cooldown_seconds), 1)
        blocked_until_ms = now_ms + (cooldown_seconds * 1000)
        blocked_until = datetime.fromtimestamp(blocked_until_ms / 1000, tz=timezone.utc).isoformat()
        retry_after_seconds = max(0, ceil((blocked_until_ms - now_ms) / 1000))
        self._protect_action_store.set_block_cooldown(
            project_id=scoped_id,
            blocked_until_ms=blocked_until_ms,
            cooldown_seconds=cooldown_seconds,
        )
        self._protect_action_store.record(project_id=scoped_id, decision="block", reason=reason)
        self._enqueue_block_webhook(
            project_id=project_id,
            provider=provider,
            reason=reason,
            requests_60s=requests_60s,
            tokens_60s=tokens_60s,
            max_req=max_req,
            max_tok=max_tok,
        )
        return ProtectDecision(
            decision="block",
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
                "decision_timeout_ms": decision_timeout_ms,
                "predictive": {
                    "enabled": False,
                    "estimated_next_tokens": None,
                    "would_exceed_tokens_cap": False,
                },
            },
        )

    def _enqueue_block_webhook(
        self,
        *,
        project_id: str,
        provider: str,
        reason: str,
        requests_60s: int,
        tokens_60s: int,
        max_req: int | None,
        max_tok: int | None,
    ) -> None:
        if self._webhook_dispatcher is None:
            return
        now = self._now_provider()
        payload = {
            "event": "incident.block",
            "project_id": project_id,
            "provider": provider,
            "incident_type": "cap_breach",
            "reason": reason,
            "requests_60s": requests_60s,
            "tokens_60s": tokens_60s,
            "req_cap": max_req,
            "tok_cap": max_tok,
            "sent_at": now.isoformat(),
        }
        try:
            self._webhook_dispatcher.enqueue(
                project_id=project_id,
                event_type="incident.block",
                payload=payload,
            )
        except Exception:
            # Decision path must never fail because webhook dispatch fails.
            pass

    def _enqueue_warn_webhook(
        self,
        *,
        project_id: str,
        provider: str,
        reason: str,
        requests_60s: int,
        tokens_60s: int,
        max_req: int | None,
        max_tok: int | None,
        estimated_next_tokens: int | None,
    ) -> None:
        if self._webhook_dispatcher is None:
            return
        now = self._now_provider()
        payload = {
            "event": "decision.warn",
            "project_id": project_id,
            "provider": provider,
            "reason": reason,
            "requests_60s": requests_60s,
            "tokens_60s": tokens_60s,
            "req_cap": max_req,
            "tok_cap": max_tok,
            "estimated_next_tokens": estimated_next_tokens,
            "sent_at": now.isoformat(),
        }
        try:
            self._webhook_dispatcher.enqueue(
                project_id=project_id,
                event_type="decision.warn",
                payload=payload,
            )
        except Exception:
            # Decision path must never fail because webhook dispatch fails.
            pass
