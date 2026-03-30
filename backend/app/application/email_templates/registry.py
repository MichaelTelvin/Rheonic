from __future__ import annotations

from typing import Callable

from app.application.email_templates.feedback_submitted import render_feedback_submitted
from app.application.email_templates.incident_block import render_incident_block
from app.application.email_templates.incident_resolved import render_incident_resolved
from app.application.email_templates.incident_warn import render_incident_warn
from app.application.email_templates.protection_block import render_protection_block
from app.application.email_templates.protection_clamp_started import render_protection_clamp_started
from app.application.email_templates.webhook_delivery_failed import render_webhook_delivery_failed

TemplateRenderer = Callable[[dict[str, object]], dict[str, str]]

_TEMPLATE_REGISTRY: dict[str, TemplateRenderer] = {
    "feedback_submitted": render_feedback_submitted,
    "incident_warn": render_incident_warn,
    "incident_block": render_incident_block,
    "protection_clamp_started": render_protection_clamp_started,
    "protection_block": render_protection_block,
    "incident_resolved": render_incident_resolved,
    "webhook_delivery_failed": render_webhook_delivery_failed,
}


def render_template(template: str, payload: dict[str, object]) -> dict[str, str]:
    renderer = _TEMPLATE_REGISTRY.get(template)
    if renderer is None:
        raise ValueError(f"unknown email template: {template}")
    return renderer(payload)
