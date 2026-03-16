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

    with pytest.raises(ValueError, match="forbidden key"):
        normalize_payload_template_json("{\"rheonic\": {\"event\": \"incident.warn\"}}")

    with pytest.raises(ValueError, match="forbidden key"):
        normalize_payload_template_json("{\"outer\": {\"constructor\": {\"x\": 1}}}")


def test_render_payload_template_appends_silent_rheonic_metadata() -> None:
    template = parse_payload_template_json(
        "{\"text\":\"agent behavior anomaly detected\",\"meta\":{\"provider\":\"openai\"}}"
    )
    assert template is not None
    rendered = render_payload_template(
        template=template,
        context={"event": "incident.warn", "incident_type": "retry_storm", "provider": "openai"},
    )
    assert rendered == {
        "meta": {"provider": "openai"},
        "rheonic": {
            "event": "incident.warn",
            "incident_type": "retry_storm",
            "provider": "openai",
        },
        "text": "agent behavior anomaly detected",
    }


def test_render_payload_template_keeps_script_like_strings_literal() -> None:
    template = parse_payload_template_json(
        "{\"text\":\"<script>alert('xss')</script>\",\"parse_mode\":\"HTML\"}"
    )
    assert template is not None
    rendered = render_payload_template(
        template=template,
        context={"event": "incident.warn", "project_id": "p1"},
    )
    assert rendered["text"] == "<script>alert('xss')</script>"
    assert rendered["parse_mode"] == "HTML"
    assert rendered["rheonic"]["event"] == "incident.warn"
