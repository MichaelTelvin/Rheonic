from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def render_incident_resolved(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    incident_id = str(payload.get("incident_id") or "-")
    incident_type = str(payload.get("incident_type") or "-")
    resolved_by = str(payload.get("resolved_by") or "-")
    resolved_at = format_timestamp(payload.get("resolved_at"))
    created_at = format_timestamp(payload.get("created_at"))
    last_seen_at = format_timestamp(payload.get("last_seen_at"))
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    sent_at = format_timestamp(payload.get("sent_at"))

    rendered = render_base_email(
        eyebrow="Protect alert",
        title="Incident resolved",
        subtitle="A previously open protect incident has been resolved.",
        fields=[
            ("Project ID", project_id),
            ("Incident ID", incident_id),
            ("Incident type", incident_type),
            ("Resolved by", resolved_by),
            ("Resolved at", resolved_at),
            ("Created at", created_at),
            ("Last seen at", last_seen_at),
            ("Provider", provider),
            ("Model", model),
            ("Environment", environment),
            ("Sent at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] incident.resolved {incident_type} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
