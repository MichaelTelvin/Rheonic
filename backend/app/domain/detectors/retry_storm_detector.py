from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
from app.domain.detectors.model_normalization import normalized_model_name
from app.domain.models.event import Event


class RetryStormDetector(Detector):
    # Detect repeated provider-side failures in a short window.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if not ctx.recent_events:
            return []
        cutoff = ctx.now.timestamp() - float(ctx.retry_storm_window_seconds)
        # Count actual failure outcomes only so retry intent/state changes do not
        # double-count a single failure episode.
        failed_events = [
            event
            for event in ctx.recent_events
            if event.provider == ctx.provider
            and normalized_model_name(event.requested_model) == normalized_model_name(ctx.requested_model)
            and event.created_at.timestamp() >= cutoff
            and _is_failure(event)
        ]
        failure_count = len(failed_events)
        if failure_count < ctx.retry_storm_count:
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "requested_model": ctx.requested_model,
            "resolved_model": ctx.resolved_model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "estimated_next_tokens": ctx.estimated_next_tokens,
            "failure_count": failure_count,
            "window_seconds": ctx.retry_storm_window_seconds,
            "threshold_count": ctx.retry_storm_count,
            "reason": "retry_storm",
        }
        return [
            Signal(
                detector="retry_storm",
                scope_provider=ctx.provider,
                fingerprint=(
                    f"{ctx.project_id}:{ctx.provider}:{normalized_model_name(ctx.requested_model) or 'na'}:retry_storm"
                ),
                evidence=evidence,
                episode_window_seconds=ctx.retry_storm_window_seconds,
                tags=_tags(ctx),
            )
        ]


def _is_failure(event: Event) -> bool:
    retryable_status = {408, 429}
    http_status = event.http_status or 0

    if isinstance(http_status, int) and (http_status >= 500 or http_status in retryable_status):
        return True

    status = (event.status or "").strip().lower()
    if status in {"error", "failed", "fail"}:
        return True

    error_type = (event.error_type or "").strip().lower()
    if any(token in error_type for token in ("timeout", "connection", "reset", "refused")):
        return True

    return False


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.requested_model:
        tags["requested_model"] = ctx.requested_model
    return tags
