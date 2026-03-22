from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, humanize_incident_type, render_base_email


def render_protection_warn(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    reason = humanize_incident_type(payload.get("reason"))
    requests_60s = str(payload.get("requests_60s") or "-")
    tokens_60s = str(payload.get("tokens_60s") or "-")
    req_cap = str(payload.get("req_cap") or "-")
    tok_cap = str(payload.get("tok_cap") or "-")
    estimated_next_tokens = str(payload.get("estimated_next_tokens") or "-")
    clamp_value = payload.get("clamp")
    clamp = clamp_value if isinstance(clamp_value, dict) else None
    clamp_copy = "-"
    if clamp is not None:
        recommended = clamp.get("recommended_max_output_tokens")
        if isinstance(recommended, int):
            clamp_copy = f"Recommended max output tokens: {recommended}"
    sent_at = format_timestamp(payload.get("sent_at"))

    rendered = render_base_email(
        eyebrow=None,
        title="Warning issued",
        subtitle="Protect detected a risky condition and allowed traffic to continue.",
        fields=[
            ("Project ID", project_id),
            ("Provider", provider),
            ("Model", model),
            ("Environment", environment),
            ("Action", "Warn"),
            ("Reason", reason),
            ("Requests / 60s", requests_60s),
            ("Tokens / 60s", tokens_60s),
            ("Request cap", req_cap),
            ("Token cap", tok_cap),
            ("Estimated next tokens", estimated_next_tokens),
            ("Clamp recommendation", clamp_copy),
            ("Sent at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] Protect alert: {reason} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
