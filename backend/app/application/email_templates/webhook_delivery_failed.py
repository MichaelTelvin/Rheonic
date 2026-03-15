from __future__ import annotations

from app.application.email_templates.base_layout import format_timestamp, render_base_email


def render_webhook_delivery_failed(payload: dict[str, object]) -> dict[str, str]:
    project_id = str(payload.get("project_id") or "-")
    event_type = str(payload.get("event_type") or "-")
    destination = str(payload.get("destination") or "-")
    status = str(payload.get("status") or "failed")
    attempts = str(payload.get("attempts") or "-")
    max_attempts = str(payload.get("max_attempts") or "-")
    last_error_code = str(payload.get("last_error_code") or "-")
    last_error_message = str(payload.get("last_error_message") or "-")
    updated_at = format_timestamp(payload.get("updated_at"))

    rendered = render_base_email(
        eyebrow="Protect alert",
        title="Webhook delivery failed",
        subtitle="A configured webhook endpoint entered a failed or dead delivery state.",
        fields=[
            ("Project ID", project_id),
            ("Event type", event_type),
            ("Destination", destination),
            ("Status", status),
            ("Attempts", attempts),
            ("Max attempts", max_attempts),
            ("Error code", last_error_code),
            ("Error message", last_error_message),
            ("Updated at", updated_at),
        ],
    )
    return {
        "subject": f"[Rheonic] webhook.delivery_failed ({project_id})",
        "html": rendered["html"],
        "text": rendered["text"],
    }
