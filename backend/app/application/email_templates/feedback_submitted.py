from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def render_feedback_submitted(payload: dict[str, object]) -> dict[str, str]:
    message = str(payload.get("message") or "").strip()
    email = str(payload.get("email") or "").strip() or "-"
    user_id = str(payload.get("user_id") or "").strip() or "-"
    user_email = str(payload.get("user_email") or "").strip() or "-"
    project_id = str(payload.get("project_id") or "").strip() or "-"
    page = str(payload.get("page") or "").strip() or "-"
    mode = str(payload.get("mode") or "").strip() or "-"
    timestamp = format_timestamp(payload.get("timestamp"))
    app_version = str(payload.get("app_version") or "").strip() or "-"

    subject = "Rheonic beta feedback"
    rendered = render_base_email(
        eyebrow="System",
        title="Rheonic beta feedback",
        subtitle="New feedback submission received.",
        fields=[
            ("message", message),
            ("email", email),
            ("user_id", user_id),
            ("user_email", user_email),
            ("project_id", project_id),
            ("page", page),
            ("mode", mode),
            ("timestamp", timestamp),
            ("app_version", app_version),
        ],
    )
    return {"subject": subject, "html": rendered["html"], "text": rendered["text"]}
