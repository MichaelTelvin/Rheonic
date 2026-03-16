from __future__ import annotations

import pytest

from app.application.webhooks.payload_template import normalize_payload_template_json, parse_payload_template_json, render_payload_template


def test_normalize_payload_template_json_returns_none_for_blank() -> None:
    assert normalize_payload_template_json(None) is None
    assert normalize_payload_template_json("   ") is None


def test_normalize_payload_template_json_rejects_non_object_root() -> None:
    with pytest.raises(ValueError, match="root must be an object"):
        normalize_payload_template_json("[1,2,3]")


def test_normalize_payload_template_json_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="must be valid JSON"):
        normalize_payload_template_json("{\"text\":")


def test_normalize_payload_template_json_rejects_forbidden_keys() -> None:
    with pytest.raises(ValueError, match="forbidden key"):
        normalize_payload_template_json("{\"__proto__\": {\"x\": 1}}")


def test_render_payload_template_interpolates_nested_values() -> None:
    template = parse_payload_template_json(
        "{\"text\":\"{{event}} {{incident_type}}\",\"meta\":{\"provider\":\"{{provider}}\",\"missing\":\"{{missing}}\"}}"
    )
    assert template is not None
    rendered = render_payload_template(
        template=template,
        context={"event": "incident.warn", "incident_type": "retry_storm", "provider": "openai"},
    )
    assert rendered == {
        "meta": {"missing": "", "provider": "openai"},
        "rheonic": {
            "attempts": "",
            "destination": "",
            "environment": "",
            "event": "incident.warn",
            "incident_id": "",
            "incident_type": "retry_storm",
            "last_error_code": "",
            "last_error_message": "",
            "max_attempts": "",
            "model": "",
            "project_id": "",
            "provider": "openai",
            "reason": "",
            "req_cap": "",
            "requests_60s": "",
            "resolved_at": "",
            "resolved_by": "",
            "sent_at": "",
            "status": "",
            "tok_cap": "",
            "tokens_60s": "",
        },
        "text": "incident.warn retry_storm",
    }
