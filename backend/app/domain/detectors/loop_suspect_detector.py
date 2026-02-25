from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class LoopSuspectDetector(Detector):
    # Detect rapid repeated traffic with the same signature.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if not ctx.recent_events:
            return []
        cutoff = ctx.now.timestamp() - float(ctx.loop_window_seconds)
        signature = _signature(ctx.provider, ctx.model, ctx.environment, ctx.current_event)
        hit_count = 0
        for event in ctx.recent_events:
            if event.provider != ctx.provider:
                continue
            if event.created_at.timestamp() < cutoff:
                continue
            event_signature = _signature(event.provider, event.model, event.environment, event)
            if event_signature == signature:
                hit_count += 1
        if hit_count < ctx.loop_count:
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
            "signature": signature,
            "window_seconds": ctx.loop_window_seconds,
            "hit_count": hit_count,
            "threshold_count": ctx.loop_count,
            "reason": "loop_suspect",
        }
        return [
            Signal(
                detector="loop_suspect",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:loop_suspect:{signature}",
                evidence=evidence,
                tags=_tags(ctx),
            )
        ]


def _signature(provider: str, model: str | None, environment: str | None, event) -> str:
    if event is None:
        return f"{provider}:{model or 'na'}:{environment or 'na'}"
    status = (event.status or "na").strip().lower()
    error = (event.error_type or "na").strip().lower()
    return f"{provider}:{model or 'na'}:{environment or 'na'}:{status}:{error}:{event.total_tokens}"


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
