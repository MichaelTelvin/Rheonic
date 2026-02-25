from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class NearCapDetector(Detector):
    # Warn detector for preflight near-cap conditions.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        if not ctx.protect_enabled:
            return []
        req_ratio = None
        tok_ratio = None
        req_near = False
        tok_near = False
        if ctx.req_cap is not None and ctx.req_cap > 0:
            req_ratio = float(ctx.current_requests_60s + 1) / float(ctx.req_cap)
            req_near = req_ratio >= ctx.warn_ratio
        if ctx.tok_cap is not None and ctx.tok_cap > 0 and ctx.estimated_next_tokens is not None:
            tok_ratio = float(ctx.current_tokens_60s + ctx.estimated_next_tokens) / float(ctx.tok_cap)
            tok_near = tok_ratio >= ctx.warn_ratio
        if not (req_near or tok_near):
            return []
        evidence: dict[str, object] = {
            "provider": ctx.provider,
            "model": ctx.model,
            "environment": ctx.environment,
            "requests_60s": ctx.current_requests_60s,
            "tokens_60s": ctx.current_tokens_60s,
            "req_cap": ctx.req_cap,
            "tok_cap": ctx.tok_cap,
            "warn_ratio": ctx.warn_ratio,
            "estimated_next_tokens": ctx.estimated_next_tokens,
            "req_ratio_to_cap": req_ratio,
            "tok_ratio_to_cap": tok_ratio,
            "reason": "near_cap",
        }
        return [
            Signal(
                detector="near_cap",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:near_cap",
                evidence=evidence,
                tags=_tags(ctx),
            )
        ]


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags
