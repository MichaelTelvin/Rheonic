from __future__ import annotations

from app.application.email_templates.base_layout import render_base_email


def render_policy_gap_detected(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    provider = str(payload.get("provider") or "-")
    model = str(payload.get("model") or "-")
    first_seen_at = str(payload.get("first_seen_at") or "-")
    sent_at = str(payload.get("sent_at") or "-")

    rendered = render_base_email(
        title="policy_gap.detected",
        subtitle="A new provider/model tuple was observed.",
        fields=[
            ("project_id", project_id),
            ("provider", provider),
            ("model", model),
            ("first_seen_at", first_seen_at),
            ("sent_at", sent_at),
        ],
    )
    return {
        "subject": f"[Rheonic] policy_gap.detected {provider}/{model} ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }

