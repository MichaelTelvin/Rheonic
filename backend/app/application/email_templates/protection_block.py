from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def _humanize_value(value: str) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return "-"
    mapping = {
        "decision_timeout": "Decision timeout",
        "decision_unavailable": "Decision unavailable",
        "timeout_fallback": "Timeout fallback",
        "unavailable_fallback": "Unavailable fallback",
        "live": "Live",
    }
    return mapping.get(normalized, normalized.replace("_", " ").replace("-", " ").title())


def _reason_copy(reason: str, detail_reason: str) -> tuple[str, str]:
    normalized = (reason or "").strip().lower()
    if normalized == "tok_cap_breach":
        return "Token cap exceeded", "Protect blocked traffic because the project crossed its configured token cap."
    if normalized == "req_cap_breach":
        return "Request cap exceeded", "Protect blocked traffic because the project crossed its configured request cap."
    if normalized == "cooldown_active":
        return "Cooldown active", "Protect blocked traffic because the project is still inside a cooldown window."
    if normalized == "fail_closed":
        return "Fail-closed fallback", "Protect blocked traffic because fail-closed fallback was exercised."
    return normalized or "-", "Protect blocked traffic."


def render_protection_block(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "").strip()
    requested_model = str(payload.get("requested_model") or "").strip()
    environment = str(payload.get("environment") or "").strip()
    reason = str(payload.get("reason") or "-")
    detail_reason = str(payload.get("detail_reason") or "-")
    requests_60s = payload.get("requests_60s")
    tokens_60s = payload.get("tokens_60s")
    req_cap = payload.get("req_cap")
    tok_cap = payload.get("tok_cap")
    blocked_until = format_timestamp(payload.get("blocked_until"))
    retry_after_seconds = payload.get("retry_after_seconds")
    retry_after_copy = ""
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        retry_after_copy = f"{retry_after_seconds} seconds"
    source = str(payload.get("source") or "").strip()
    sent_at = format_timestamp(payload.get("sent_at"))
    reason_title, reason_subtitle = _reason_copy(reason, detail_reason)
    detail_reason_copy = _humanize_value(detail_reason)
    source_copy = _humanize_value(source)

    fields: list[tuple[str, str]] = [
        ("Project ID", project_id),
        ("Action", "Blocked"),
        ("Reason", reason_title),
        ("Detail reason", detail_reason_copy),
    ]
    if provider:
        fields.append(("Provider", provider))
    if requested_model:
        fields.append(("Model", requested_model))
    if environment:
        fields.append(("Environment", environment))
    if isinstance(requests_60s, int):
        fields.append(("Requests / 60s", str(requests_60s)))
    if isinstance(tokens_60s, int):
        fields.append(("Tokens / 60s", str(tokens_60s)))
    if isinstance(req_cap, int):
        fields.append(("Request cap", str(req_cap)))
    if isinstance(tok_cap, int):
        fields.append(("Token cap", str(tok_cap)))
    if blocked_until != "-":
        fields.append(("Blocked until", blocked_until))
    if retry_after_copy:
        fields.append(("Retry after", retry_after_copy))
    if source:
        fields.append(("Source", source_copy))
    if sent_at != "-":
        fields.append(("Sent at", sent_at))

    rendered = render_base_email(
        eyebrow=None,
        title="Blocked traffic",
        subtitle=reason_subtitle,
        fields=fields,
    )
    return {
        "subject": f"[Rheonic] Protect alert: {reason_title} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
