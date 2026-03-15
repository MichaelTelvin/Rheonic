from __future__ import annotations

import json

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def render_incident_warn(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    incident_id = str(payload.get("incident_id") or "-")
    incident_type = str(payload.get("incident_type") or "-")
    provider = str(payload.get("provider") or "-")
    created_at = format_timestamp(payload.get("created_at"))
    last_seen_at = format_timestamp(payload.get("last_seen_at"))
    sent_at = format_timestamp(payload.get("sent_at"))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    evidence_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"))

    rendered = render_base_email(
        eyebrow="Protect alert",
        title="Incident warning opened",
        subtitle="Rheonic detected a protect incident that is warning-level and non-blocking.",
        fields=[
            ("Project ID", project_id),
            ("Incident ID", incident_id),
            ("Incident type", incident_type),
            ("Provider", provider),
            ("Action", "Warn"),
            ("Created at", created_at),
            ("Last seen at", last_seen_at),
            ("Sent at", sent_at),
            ("Evidence", evidence_json),
        ],
    )
    return {
        "subject": f"[Rheonic] incident.warn {incident_type} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
