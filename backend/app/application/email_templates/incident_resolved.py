from __future__ import annotations

from app.application.email_templates.base_layout import render_base_email


def render_incident_resolved(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    incident_id = str(payload.get("incident_id") or "-")
    incident_type = str(payload.get("incident_type") or "-")
    resolved_by = str(payload.get("resolved_by") or "-")
    resolved_at = str(payload.get("resolved_at") or "-")
    created_at = str(payload.get("created_at") or "-")
    last_seen_at = str(payload.get("last_seen_at") or "-")
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    environment = str(payload.get("environment") or "-")
    sent_at = str(payload.get("sent_at") or "-")

    rendered = render_base_email(
        title="incident.resolved",
        subtitle="An incident was resolved.",
        fields=[
            ("project_id", project_id),
            ("incident_id", incident_id),
            ("incident_type", incident_type),
            ("resolved_by", resolved_by),
            ("resolved_at", resolved_at),
            ("created_at", created_at),
            ("last_seen_at", last_seen_at),
            ("provider", provider),
            ("model", model),
            ("environment", environment),
            ("sent_at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] incident.resolved {incident_type} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }

