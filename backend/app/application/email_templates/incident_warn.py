from __future__ import annotations

import json

from app.application.email_templates.base_layout import render_base_email


def render_incident_warn(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    incident_id = str(payload.get("incident_id") or "-")
    incident_type = str(payload.get("incident_type") or "-")
    provider = str(payload.get("provider") or "-")
    created_at = str(payload.get("created_at") or "-")
    last_seen_at = str(payload.get("last_seen_at") or "-")
    sent_at = str(payload.get("sent_at") or "-")
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    evidence_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"))

    rendered = render_base_email(
        title="incident.warn",
        subtitle="A non-blocking incident was opened in protect mode.",
        fields=[
            ("project_id", project_id),
            ("incident_id", incident_id),
            ("incident_type", incident_type),
            ("provider", provider),
            ("created_at", created_at),
            ("last_seen_at", last_seen_at),
            ("sent_at", sent_at),
            ("evidence", evidence_json),
        ],
    )
    return {
        "subject": f"[Rheonic] incident.warn {incident_type} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }

