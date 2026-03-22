from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, humanize_incident_type, render_base_email


def render_protection_clamp_started(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    reason = humanize_incident_type(payload.get("reason"))
    clamp_value = payload.get("clamp")
    clamp = clamp_value if isinstance(clamp_value, dict) else {}
    recommended = clamp.get("recommended_max_output_tokens")
    recommended_copy = str(recommended) if isinstance(recommended, int) else "-"
    requests_60s = str(payload.get("requests_60s") or "-")
    tokens_60s = str(payload.get("tokens_60s") or "-")
    req_cap = str(payload.get("req_cap") or "-")
    tok_cap = str(payload.get("tok_cap") or "-")
    estimated_next_tokens = str(payload.get("estimated_next_tokens") or "-")
    sent_at = format_timestamp(payload.get("sent_at"))

    rendered = render_base_email(
        eyebrow=None,
        title="Clamp started",
        subtitle="Protect is actively reducing output to keep traffic within the configured budget.",
        fields=[
            ("Project ID", project_id),
            ("Provider", provider),
            ("Model", model),
            ("Environment", environment),
            ("Action", "Clamp"),
            ("Reason", reason),
            ("Recommended max output tokens", recommended_copy),
            ("Requests / 60s", requests_60s),
            ("Tokens / 60s", tokens_60s),
            ("Request cap", req_cap),
            ("Token cap", tok_cap),
            ("Estimated next tokens", estimated_next_tokens),
            ("Sent at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] Protect alert: Clamp started - {reason} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
