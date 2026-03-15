# Application service for protect mode decision and project protect settings.
from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from time import perf_counter
from typing import Callable

from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.application.interfaces.webhook_dispatcher import WebhookDispatcher
from app.application.provider_scope import scoped_project_provider_id
from app.application.services.ingest_key_service import IngestKeyService
from app.application.services.transport_service import TransportService, build_transport_dedupe_key
from app.config import Settings, app_config
from app.domain.detectors.contracts import DetectionContext
from app.domain.detectors.loop_suspect_detector import LoopSuspectDetector
from app.domain.detectors.near_cap_detector import NearCapDetector
from app.domain.detectors.registry import DetectorRegistry
from app.domain.detectors.retry_storm_detector import RetryStormDetector
from app.domain.detectors.token_explosion_detector import TokenExplosionDetector
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
    apply_clamp_enabled: bool
    clamp: dict[str, int | bool] | None = None


@dataclass(slots=True)
class ProtectDecisionContext:
    # Optional request context used for proactive predictive warning.
    max_output_tokens: int | None = None
    input_tokens_estimate: int | None = None
    environment: str | None = None
    provider: str | None = None
    model: str | None = None
    feature: str | None = None


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
        transport_service: TransportService | None = None,
        now_provider: Callable[[], datetime] | None = None,
        protect_decision_timeout_ms: int | None = None,
    ) -> None:
        self._ingest_key_service = ingest_key_service
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters
        self._protect_action_store = protect_action_store
        self._protect_block_cooldown_seconds = protect_block_cooldown_seconds
        self._webhook_dispatcher = webhook_dispatcher
        self._transport_service = transport_service
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._protect_decision_timeout_ms = int(
            protect_decision_timeout_ms
            if protect_decision_timeout_ms is not None
            else Settings().protect_decision_timeout_ms
        )
        self._fast_warn_detector_registry = DetectorRegistry(detectors=[NearCapDetector()])
        self._behavioral_warn_detector_registry = DetectorRegistry(
            detectors=[
                RetryStormDetector(),
                LoopSuspectDetector(),
            ]
        )
        self._deferred_warn_detector_registry = DetectorRegistry(detectors=[TokenExplosionDetector()])

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
        apply_clamp_enabled = bool(project.apply_clamp)
        decision_timeout_ms = self._protect_decision_timeout_ms
        requests_60s, tokens_60s = self._realtime_counters.get_project_60s(project_id=scoped_id)

        if not project.protect_enabled:
            decision = "allow"
            reason = "ok"
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
                apply_clamp_enabled=apply_clamp_enabled,
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
                apply_clamp_enabled=apply_clamp_enabled,
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
                apply_clamp_enabled=apply_clamp_enabled,
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
                apply_clamp_enabled=apply_clamp_enabled,
            )

        estimated_next_tokens: int | None = None
        if isinstance(ctx.input_tokens_estimate, int):
            input_estimate = max(ctx.input_tokens_estimate, 0)
            output_estimate = max(ctx.max_output_tokens, 0) if isinstance(ctx.max_output_tokens, int) else 0
            estimated_next_tokens = input_estimate + output_estimate
        detector_ctx = DetectionContext(
            project_id=project_id,
            provider=provider,
            model=ctx.model,
            environment=ctx.environment,
            request_endpoint="/chat/completions",
            request_feature=ctx.feature,
            now=now,
            current_requests_60s=requests_60s,
            current_tokens_60s=tokens_60s,
            req_cap=max_req,
            tok_cap=max_tok,
            protect_enabled=True,
            estimated_next_tokens=estimated_next_tokens,
            current_event=None,
            recent_events=[],
            warn_ratio=app_config.protect_near_cap_factor,
            retry_storm_window_seconds=app_config.retry_storm_window_seconds,
            retry_storm_count=app_config.retry_storm_count,
            loop_window_seconds=app_config.loop_window_seconds,
            loop_count=app_config.loop_count,
            token_explosion_ratio=app_config.token_explosion_ratio,
            token_explosion_abs=app_config.token_explosion_abs,
        )
        warn_signals = self._fast_warn_detector_registry.detect(detector_ctx)
        if warn_signals:
            warn_signal = warn_signals[0]
            reason = str(warn_signal.detector)
            clamp = self._build_clamp(
                reason=reason,
                max_tok=max_tok,
                current_tokens_60s=tokens_60s,
                max_output_tokens=ctx.max_output_tokens,
                estimated_next_tokens=estimated_next_tokens,
            )
            self._enqueue_warn_webhook(
                project_id=project_id,
                provider=provider,
                reason=reason,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                estimated_next_tokens=estimated_next_tokens,
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
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
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
            )

        recent_events = []
        if self._event_repository is not None:
            recent_limit = max(int(app_config.retry_storm_count), int(app_config.loop_count)) + 8
            recent_fetch_started_at = perf_counter()
            recent_events = self._event_repository.list_recent(project_id=project_id, limit=recent_limit, provider=provider)
            logger.debug(
                "Loaded recent events for protect evaluation",
                extra={
                    "project_id": project_id,
                    "provider": provider,
                    "recent_events_count": len(recent_events),
                    "recent_events_fetch_ms": int((perf_counter() - recent_fetch_started_at) * 1000),
                },
            )
        detector_ctx = DetectionContext(
            project_id=project_id,
            provider=provider,
            model=ctx.model,
            environment=ctx.environment,
            request_endpoint="/chat/completions",
            request_feature=ctx.feature,
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
        warn_signals = self._behavioral_warn_detector_registry.detect(detector_ctx)
        if warn_signals:
            warn_signal = warn_signals[0]
            reason = str(warn_signal.detector)
            clamp = self._build_clamp(
                reason=reason,
                max_tok=max_tok,
                current_tokens_60s=tokens_60s,
                max_output_tokens=ctx.max_output_tokens,
                estimated_next_tokens=estimated_next_tokens,
            )
            self._enqueue_warn_webhook(
                project_id=project_id,
                provider=provider,
                reason=reason,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                estimated_next_tokens=estimated_next_tokens,
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
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
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
            )

        warn_signals = self._deferred_warn_detector_registry.detect(detector_ctx)
        if warn_signals:
            warn_signal = warn_signals[0]
            reason = str(warn_signal.detector)
            clamp = self._build_clamp(
                reason=reason,
                max_tok=max_tok,
                current_tokens_60s=tokens_60s,
                max_output_tokens=ctx.max_output_tokens,
                estimated_next_tokens=estimated_next_tokens,
            )
            self._enqueue_warn_webhook(
                project_id=project_id,
                provider=provider,
                reason=reason,
                requests_60s=requests_60s,
                tokens_60s=tokens_60s,
                max_req=max_req,
                max_tok=max_tok,
                estimated_next_tokens=estimated_next_tokens,
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
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
                apply_clamp_enabled=apply_clamp_enabled,
                clamp=clamp,
            )

        decision = "allow"
        reason = "ok"
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
            apply_clamp_enabled=apply_clamp_enabled,
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
        apply_clamp_enabled: bool,
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
        self._enqueue_block_notifications(
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
            apply_clamp_enabled=apply_clamp_enabled,
        )

    def _enqueue_block_notifications(
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
        if self._webhook_dispatcher is not None:
            try:
                self._webhook_dispatcher.enqueue(
                    project_id=project_id,
                    event_type="incident.block",
                    payload=payload,
                )
            except Exception:
                # Decision path must never fail because webhook dispatch fails.
                logger.exception(
                    "Failed to enqueue protect block webhook",
                    extra={"project_id": project_id, "provider": provider, "reason": reason},
                )
        if self._transport_service is None:
            return
        try:
            dedupe_key = build_transport_dedupe_key(
                project_id=project_id,
                kind="email",
                event_type="incident.block",
                payload=payload,
                seed=reason,
            )
            self._transport_service.enqueue(
                project_id=project_id,
                kind="email",
                event_type="incident.block",
                payload=payload,
                dedupe_key=dedupe_key,
                template="incident_block",
                provider=provider,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue protect block email",
                extra={"project_id": project_id, "provider": provider, "reason": reason},
            )

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
        apply_clamp_enabled: bool,
        clamp: dict[str, int | bool] | None,
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
            "apply_clamp_enabled": apply_clamp_enabled,
            "clamp": clamp,
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
            logger.exception(
                "Failed to enqueue protect warn webhook",
                extra={"project_id": project_id, "provider": provider, "reason": reason},
            )

    def _build_clamp(
        self,
        *,
        reason: str,
        max_tok: int | None,
        current_tokens_60s: int,
        max_output_tokens: int | None,
        estimated_next_tokens: int | None,
    ) -> dict[str, int | bool] | None:
        if reason != "near_cap":
            return None
        if max_tok is None or max_tok <= 0:
            return None
        if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
            return None
        if not isinstance(estimated_next_tokens, int):
            return None
        input_estimate = estimated_next_tokens - max_output_tokens
        if input_estimate < 0:
            input_estimate = 0
        available_for_output = max_tok - current_tokens_60s - input_estimate
        if available_for_output < 1:
            recommended = 1
        else:
            recommended = min(max_output_tokens, available_for_output)
        return {
            "recommended_max_output_tokens": int(recommended),
            "applied": False,
        }
