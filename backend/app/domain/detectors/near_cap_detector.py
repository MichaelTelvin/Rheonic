from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class NearCapDetector(Detector):
    # Warn detector for preflight near-cap conditions.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        req_ratio = None
        tok_ratio = None
        req_near = False
        tok_near = False
        req_numerator = ctx.current_requests_60s + (1 if ctx.predictive_near_cap else 0)
        tok_numerator = ctx.current_tokens_60s
        if ctx.predictive_near_cap and ctx.estimated_next_tokens is not None:
            tok_numerator += ctx.estimated_next_tokens
        if ctx.req_cap is not None and ctx.req_cap > 0:
            req_ratio = float(req_numerator) / float(ctx.req_cap)
            req_near = req_ratio >= ctx.warn_ratio
        if ctx.tok_cap is not None and ctx.tok_cap > 0:
            tok_ratio = float(tok_numerator) / float(ctx.tok_cap)
            tok_near = tok_ratio >= ctx.warn_ratio
        if not (req_near or tok_near):
            return []
        near_cap_type = "both" if req_near and tok_near else ("req" if req_near else "tok")
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
            "req_ratio_to_cap": _round_ratio(req_ratio),
            "tok_ratio_to_cap": _round_ratio(tok_ratio),
            "req_near_cap": req_near,
            "tok_near_cap": tok_near,
            "near_cap_type": near_cap_type,
            "reason": "near_cap",
        }
        return [
            Signal(
                detector="near_cap",
                scope_provider=ctx.provider,
                fingerprint=f"{ctx.project_id}:{ctx.provider}:near_cap:{near_cap_type}",
                evidence=evidence,
                tags=_tags(ctx),
            )
        ]


def _tags(ctx: DetectionContext) -> dict[str, str]:
    tags: dict[str, str] = {}
    if ctx.model:
        tags["model"] = ctx.model
    return tags


def _round_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)
