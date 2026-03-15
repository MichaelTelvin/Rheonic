from app.application.email_templates.base_layout import format_timestamp
from app.application.email_templates.base_layout import format_evidence, humanize_incident_type
from app.application.email_templates.registry import render_template
import pytest


def test_format_timestamp_renders_human_readable_utc() -> None:
    assert format_timestamp("2026-03-05T10:00:00Z") == "Mar 05, 2026 10:00 UTC"
    assert format_timestamp("2026-03-05T10:00:00+00:00") == "Mar 05, 2026 10:00 UTC"
    assert format_timestamp("") == "-"
    assert format_timestamp(None) == "-"


def test_email_template_helpers_render_human_readable_values() -> None:
    assert humanize_incident_type("retry_storm") == "Retry storm"
    assert humanize_incident_type("cap_breach") == "Cap breach"
    evidence_copy = format_evidence({
        "count": 1,
        "provider": "openai",
        "last_seen_at": "2026-03-15T18:28:46.668971+00:00",
    })
    assert "Count: 1" in evidence_copy
    assert "Provider: openai" in evidence_copy
    assert "Last Seen At: Mar 15, 2026 18:28 UTC" in evidence_copy


def test_feedback_template_snapshot_is_deterministic() -> None:
    payload = {
        "message": "Need dark mode",
        "email": "u@example.com",
        "user_id": "u1",
        "user_email": "u@example.com",
        "project_id": "p1",
        "page": "/dashboard",
        "mode": "protect",
        "timestamp": "2026-03-05T10:00:00Z",
        "app_version": "1.2.3",
    }
    rendered = render_template("feedback_submitted", payload)
    assert rendered["subject"] == "Rheonic beta feedback"
    assert "Rheonic beta feedback" in rendered["html"]
    assert "New feedback submission received." in rendered["html"]
    assert "System" in rendered["html"]
    assert "Mar 05, 2026 10:00 UTC" in rendered["html"]
    assert "timestamp: Mar 05, 2026 10:00 UTC" in rendered["text"]
    assert render_template("feedback_submitted", payload) == rendered


def test_operational_templates_snapshots_are_deterministic() -> None:
    cases = [
        (
            "incident_warn",
            {
                "project_id": "p1",
                "incident_id": "inc-1",
                "incident_type": "retry_storm",
                "provider": "anthropic",
                "created_at": "2026-03-05T10:00:00Z",
                "last_seen_at": "2026-03-05T10:01:00Z",
                "sent_at": "2026-03-05T10:01:10Z",
                "evidence": {"count": 3, "window_seconds": 60},
            },
            "[Rheonic] Warning: Retry storm (p1)",
            "Incident warning opened",
            "Action: Warn",
        ),
        (
            "incident_block",
            {
                "project_id": "p2",
                "provider": "google",
                "reason": "tok_cap_breach",
                "requests_60s": 2,
                "tokens_60s": 2000,
                "req_cap": 100,
                "tok_cap": 1500,
                "blocked_until": "2026-03-05T10:01:00Z",
                "retry_after_seconds": 60,
                "sent_at": "2026-03-05T10:00:00Z",
            },
            "[Rheonic] Blocked: Token cap exceeded (p2)",
            "Provider traffic blocked",
            "Action: Blocked",
        ),
        (
            "incident_resolved",
            {
                "project_id": "p3",
                "incident_id": "inc-2",
                "incident_type": "loop_suspect",
                "resolved_by": "auto",
                "resolved_at": "2026-03-05T10:04:00Z",
                "created_at": "2026-03-05T10:00:00Z",
                "last_seen_at": "2026-03-05T10:03:00Z",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "environment": "prod",
                "sent_at": "2026-03-05T10:04:01Z",
            },
            "[Rheonic] Resolved: Loop suspect (p3)",
            "Incident resolved",
            "Resolved by: auto",
        ),
        (
            "webhook_delivery_failed",
            {
                "project_id": "p4",
                "event_type": "incident.warn",
                "destination": "https://example.test/hook",
                "status": "dead",
                "attempts": 3,
                "max_attempts": 3,
                "last_error_code": "webhook_http_error",
                "last_error_message": "HTTP 500",
                "updated_at": "2026-03-05T10:10:00Z",
            },
            "[Rheonic] webhook.delivery_failed (p4)",
            "Webhook delivery failed",
            "Error code: webhook_http_error",
        ),
    ]

    for template, payload, subject, expected_title, expected_text_line in cases:
        rendered = render_template(template, payload)
        assert rendered["subject"] == subject
        assert expected_title in rendered["html"]
        assert expected_text_line in rendered["text"]
        assert "Rheonic" in rendered["html"]
        assert "Protect alert" in rendered["html"]
        assert "UTC" in rendered["text"]
        assert render_template(template, payload) == rendered

    warn_rendered = render_template(
        "incident_warn",
        {
            "project_id": "p1",
            "incident_id": "inc-1",
            "incident_type": "retry_storm",
            "provider": "openai",
            "created_at": "2026-03-05T10:00:00Z",
            "last_seen_at": "2026-03-05T10:01:00Z",
            "sent_at": "2026-03-05T10:01:10Z",
            "evidence": {
                "count": 1,
                "environment": "staging-test",
                "estimated_next_tokens": 50,
                "failure_count": 5,
                "last_seen_at": "2026-03-15T18:28:46.668971+00:00",
                "model": "gpt-4o-mini",
                "provider": "openai",
                "reason": "retry_storm",
                "req_cap": 400,
                "requests_60s": 5,
                "threshold_count": 5,
                "tok_cap": 1700,
                "tokens_60s": 250,
                "window_seconds": 60,
            },
        },
    )
    assert "Incident type: Retry storm" in warn_rendered["text"]
    assert "Evidence: Reason: retry_storm" in warn_rendered["text"]
    assert "Estimated Next Tokens: 50" in warn_rendered["text"]
    assert "Last Seen At: Mar 15, 2026 18:28 UTC" in warn_rendered["text"]


def test_removed_templates_are_not_registered() -> None:
    with pytest.raises(ValueError, match="unknown email template: decision_warn"):
        render_template("decision_warn", {})
    with pytest.raises(ValueError, match="unknown email template: policy_gap_detected"):
        render_template("policy_gap_detected", {})
