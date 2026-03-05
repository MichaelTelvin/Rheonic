from __future__ import annotations

from app.application.email_templates.base_layout import render_base_email


def render_incident_block(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    reason = str(payload.get("reason") or "-")
    requests_60s = str(payload.get("requests_60s") or "-")
    tokens_60s = str(payload.get("tokens_60s") or "-")
    req_cap = str(payload.get("req_cap") or "-")
    tok_cap = str(payload.get("tok_cap") or "-")
    sent_at = str(payload.get("sent_at") or "-")

    rendered = render_base_email(
        title="incident.block",
        subtitle="Protect preflight blocked provider traffic.",
        fields=[
            ("project_id", project_id),
            ("provider", provider),
            ("reason", reason),
            ("requests_60s", requests_60s),
            ("tokens_60s", tokens_60s),
            ("req_cap", req_cap),
            ("tok_cap", tok_cap),
            ("sent_at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] incident.block {reason} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }

