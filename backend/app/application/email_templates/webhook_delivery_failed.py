from __future__ import annotations

from app.application.email_templates.base_layout import render_base_email


def render_webhook_delivery_failed(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    event_type = str(payload.get("event_type") or "-")
    destination = str(payload.get("destination") or "-")
    status = str(payload.get("status") or "failed")
    attempts = str(payload.get("attempts") or "-")
    max_attempts = str(payload.get("max_attempts") or "-")
    last_error_code = str(payload.get("last_error_code") or "-")
    last_error_message = str(payload.get("last_error_message") or "-")
    updated_at = str(payload.get("updated_at") or "-")

    rendered = render_base_email(
        title="webhook.delivery_failed",
        subtitle="Webhook delivery entered a failed or dead state.",
        fields=[
            ("project_id", project_id),
            ("event_type", event_type),
            ("destination", destination),
            ("status", status),
            ("attempts", attempts),
            ("max_attempts", max_attempts),
            ("last_error_code", last_error_code),
            ("last_error_message", last_error_message),
            ("updated_at", updated_at),
        ],
    )
    return {
        "subject": f"[Rheonic] webhook.delivery_failed ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }

