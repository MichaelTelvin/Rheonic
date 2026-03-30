from __future__ import annotations

from app.application.email_templates.base_layout import (
    format_evidence,
    format_timestamp,
    humanize_incident_type,
    render_base_email,
)


def render_incident_block(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    incident_id = str(payload.get("incident_id") or "-")
    incident_type = humanize_incident_type(payload.get("incident_type"))
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    created_at = format_timestamp(payload.get("created_at"))
    last_seen_at = format_timestamp(payload.get("last_seen_at"))
    evidence = format_evidence(payload.get("evidence"))

    rendered = render_base_email(
        eyebrow=None,
        title="Protect block incident opened",
        subtitle="Rheonic protect enforcement blocked traffic because the project crossed a configured cap.",
        fields=[
            ("Project ID", project_id),
            ("Incident ID", incident_id),
            ("Incident type", incident_type),
            ("Provider", provider),
            ("Model", model),
            ("Environment", environment),
            ("Created at", created_at),
            ("Last seen at", last_seen_at),
            ("Evidence", evidence),
        ],
    )
    return {
        "subject": f"[Rheonic] Incident opened: {incident_type} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
