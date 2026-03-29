from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
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
            and (event.model or "") == (ctx.model or "")
            and event.created_at.timestamp() >= cutoff
            and _is_failure(event)
        ]
        failure_count = len(failed_events)
        if failure_count < ctx.retry_storm_count:
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
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
                fingerprint=f"{ctx.project_id}:{ctx.provider}:retry_storm",
                evidence=evidence,
                episode_window_seconds=ctx.retry_storm_window_seconds,
                tags=_tags(ctx),
            )
        ]


def _is_failure(event: Event) -> bool:
    http_status = event.http_status or 0
    if isinstance(http_status, int) and http_status >= 500:
        return True
    status = (event.status or "").strip().lower()
    if status in {"error", "failed", "fail"}:
        return True
    return bool(event.error_type)


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
