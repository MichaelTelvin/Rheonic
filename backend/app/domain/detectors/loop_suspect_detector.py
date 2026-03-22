from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector
from app.domain.models.event import Event


class LoopSuspectDetector(Detector):
    # Detect rapid repeated traffic with the same signature.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if not ctx.recent_events or _is_error_event(ctx.current_event):
            return []
        cutoff = ctx.now.timestamp() - float(ctx.loop_window_seconds)
        signature = _context_signature(ctx)
        hit_count = 0
        for event in ctx.recent_events:
            if event.provider != ctx.provider:
                continue
            if event.created_at.timestamp() < cutoff:
                continue
            if _is_error_event(event):
                continue
            event_signature = _signature(
                project_id=ctx.project_id,
                provider=event.provider,
                model=event.model,
                environment=event.environment,
                event=event,
            )
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


def _signature(
    *,
    project_id: str,
    provider: str,
    model: str | None,
    environment: str | None,
    event: Event | None,
) -> str:
    if event is None:
        return f"{project_id}:{provider}:{model or 'na'}:{environment or 'na'}:na:unknown"
    endpoint = (event.request_endpoint or "na").strip()
    feature = (event.request_feature or "unknown").strip() or "unknown"
    return f"{project_id}:{provider}:{model or 'na'}:{environment or 'na'}:{endpoint}:{feature}"


def _context_signature(ctx: DetectionContext) -> str:
    endpoint = (ctx.request_endpoint or "na").strip()
    feature = (ctx.request_feature or "unknown").strip() or "unknown"
    return f"{ctx.project_id}:{ctx.provider}:{ctx.model or 'na'}:{ctx.environment or 'na'}:{endpoint}:{feature}"


def _is_error_event(event: Event | None) -> bool:
    if event is None:
        return False
    status = (event.status or "").strip().lower()
    if status and status != "ok":
        return True
    http_status = int(event.http_status or 0)
    if http_status >= 400:
        return True
    return bool(event.error_type)


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
