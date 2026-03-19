from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def _reason_copy(reason: str, detail_reason: str) -> tuple[str, str]:
    normalized = (reason or "").strip().lower()
    detail = (detail_reason or "").strip().lower()
    if normalized == "cap_breach":
        if detail == "tok_cap_breach":
            return "Token cap exceeded", "Protect blocked traffic because the project crossed its configured token cap."
        if detail == "req_cap_breach":
            return "Request cap exceeded", "Protect blocked traffic because the project crossed its configured request cap."
        return "Cap breach", "Protect blocked traffic because the project crossed a configured cap."
    if normalized == "cooldown_active":
        return "Cooldown active", "Protect blocked traffic because the project is still inside a cooldown window."
    if normalized == "fail_closed":
        return "Fail-closed fallback", "Protect blocked traffic because fail-closed fallback was exercised."
    return normalized or "-", "Protect blocked traffic."


def render_protection_block(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    reason = str(payload.get("reason") or "-")
    detail_reason = str(payload.get("detail_reason") or "-")
    requests_60s = str(payload.get("requests_60s") or "-")
    tokens_60s = str(payload.get("tokens_60s") or "-")
    req_cap = str(payload.get("req_cap") or "-")
    tok_cap = str(payload.get("tok_cap") or "-")
    blocked_until = format_timestamp(payload.get("blocked_until"))
    retry_after_seconds = payload.get("retry_after_seconds")
    retry_after_copy = "-"
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        retry_after_copy = f"{retry_after_seconds} seconds"
    source = str(payload.get("source") or "-")
    sent_at = format_timestamp(payload.get("sent_at"))
    reason_title, reason_subtitle = _reason_copy(reason, detail_reason)

    rendered = render_base_email(
        eyebrow=None,
        title="Blocked traffic",
        subtitle=reason_subtitle,
        fields=[
            ("Project ID", project_id),
            ("Provider", provider),
            ("Model", model),
            ("Environment", environment),
            ("Action", "Blocked"),
            ("Reason", reason_title),
            ("Detail reason", detail_reason),
            ("Requests / 60s", requests_60s),
            ("Tokens / 60s", tokens_60s),
            ("Request cap", req_cap),
            ("Token cap", tok_cap),
            ("Blocked until", blocked_until),
            ("Retry after", retry_after_copy),
            ("Source", source),
            ("Sent at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] Protect alert: {reason_title} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
