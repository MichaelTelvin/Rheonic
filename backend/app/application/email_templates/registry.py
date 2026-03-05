from __future__ import annotations

from typing import Callable

from app.application.email_templates.feedback_submitted import render_feedback_submitted

TemplateRenderer = Callable[[dict[str, object]], dict[str, str]]

_TEMPLATE_REGISTRY: dict[str, TemplateRenderer] = {
    "feedback_submitted": render_feedback_submitted,
}


def render_template(template: str, payload: dict[str, object]) -> dict[str, str]:
    renderer = _TEMPLATE_REGISTRY.get(template)
    if renderer is None:
        raise ValueError(f"unknown email template: {template}")
    return renderer(payload)
