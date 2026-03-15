from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def _reason_copy(reason: str) -> tuple[str, str]:
    normalized = (reason or "").strip().lower()
    if normalized == "tok_cap_breach":
        return "Token cap exceeded", "The project crossed its configured token limit."
    if normalized == "req_cap_breach":
        return "Request cap exceeded", "The project crossed its configured request-rate limit."
    if normalized == "cooldown_active":
        return "Cooldown active", "Protect is still in the cooldown window from a previous block."
    return normalized or "-", "Protect blocked provider traffic because a project cap was exceeded."


def render_incident_block(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    reason = str(payload.get("reason") or "-")
    requests_60s = str(payload.get("requests_60s") or "-")
    tokens_60s = str(payload.get("tokens_60s") or "-")
    req_cap = str(payload.get("req_cap") or "-")
    tok_cap = str(payload.get("tok_cap") or "-")
    blocked_until = format_timestamp(payload.get("blocked_until"))
    retry_after_seconds = payload.get("retry_after_seconds")
    sent_at = format_timestamp(payload.get("sent_at"))
    reason_title, reason_subtitle = _reason_copy(reason)
    retry_after_copy = "-"
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        retry_after_copy = f"{retry_after_seconds} seconds"

    rendered = render_base_email(
        eyebrow="Protect alert",
        title="Provider traffic blocked",
        subtitle=reason_subtitle,
        fields=[
            ("Project ID", project_id),
            ("Provider", provider),
            ("Action", "Blocked"),
            ("Reason", reason_title),
            ("Requests / 60s", requests_60s),
            ("Tokens / 60s", tokens_60s),
            ("Request cap", req_cap),
            ("Token cap", tok_cap),
            ("Blocked until", blocked_until),
            ("Retry after", retry_after_copy),
            ("Sent at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] Blocked: {reason_title} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
