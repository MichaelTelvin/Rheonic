from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def render_feedback_submitted(payload: dict[str, object]) -> dict[str, str]:
    report_type = str(payload.get("report_type") or "").strip() or "feedback"
    message = str(payload.get("message") or "").strip()
    email = str(payload.get("email") or "").strip() or "-"
    user_id = str(payload.get("user_id") or "").strip() or "-"
    user_email = str(payload.get("user_email") or "").strip() or "-"
    project_id = str(payload.get("project_id") or "").strip() or "-"
    page = str(payload.get("page") or "").strip() or "-"
    mode = str(payload.get("mode") or "").strip() or "-"
    timestamp = format_timestamp(payload.get("timestamp"))
    app_version = str(payload.get("app_version") or "").strip() or "-"
    has_screenshot = bool(str(payload.get("screenshot_name") or "").strip())

    report_label = "Bug report" if report_type == "bug" else "Product feedback"
    subject = f"Rheonic beta {report_label.lower()}"
    rendered = render_base_email(
        eyebrow="System",
        title=f"Rheonic beta {report_label.lower()}",
        subtitle="New product report received.",
        fields=[
            ("report_type", report_label),
            ("message", message),
            ("email", email),
            ("user_id", user_id),
            ("user_email", user_email),
            ("project_id", project_id),
            ("page", page),
            ("mode", mode),
            ("timestamp", timestamp),
            ("app_version", app_version),
            ("screenshot", "Attached" if has_screenshot else "-"),
        ],
    )
    return {"subject": subject, "html": rendered["html"], "text": rendered["text"]}
