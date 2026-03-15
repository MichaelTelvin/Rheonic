from app.application.email_templates.registry import render_template
import pytest


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
    expected = {
        "subject": "Rheonic beta feedback",
        "html": "<!doctype html><html><body><h2>Rheonic beta feedback</h2><p>New feedback submission received.</p><table><tr><td><strong>message</strong></td><td>Need dark mode</td></tr><tr><td><strong>email</strong></td><td>u@example.com</td></tr><tr><td><strong>user_id</strong></td><td>u1</td></tr><tr><td><strong>user_email</strong></td><td>u@example.com</td></tr><tr><td><strong>project_id</strong></td><td>p1</td></tr><tr><td><strong>page</strong></td><td>/dashboard</td></tr><tr><td><strong>mode</strong></td><td>protect</td></tr><tr><td><strong>timestamp</strong></td><td>2026-03-05T10:00:00Z</td></tr><tr><td><strong>app_version</strong></td><td>1.2.3</td></tr></table></body></html>",
        "text": "Rheonic beta feedback\nNew feedback submission received.\n\nmessage: Need dark mode\nemail: u@example.com\nuser_id: u1\nuser_email: u@example.com\nproject_id: p1\npage: /dashboard\nmode: protect\ntimestamp: 2026-03-05T10:00:00Z\napp_version: 1.2.3",
    }
    assert rendered == expected
    assert render_template("feedback_submitted", payload) == expected


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
            "[Rheonic] incident.warn retry_storm (p1)",
            'evidence: {"count":3,"window_seconds":60}',
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
                "sent_at": "2026-03-05T10:00:00Z",
            },
            "[Rheonic] incident.block tok_cap_breach (p2)",
            "tokens_60s: 2000",
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
            "[Rheonic] incident.resolved loop_suspect (p3)",
            "resolved_by: auto",
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
            "last_error_code: webhook_http_error",
        ),
    ]

    for template, payload, subject, expected_text_line in cases:
        rendered = render_template(template, payload)
        assert rendered["subject"] == subject
        assert expected_text_line in rendered["text"]
        assert rendered["html"].startswith("<!doctype html><html><body><h2>")
        assert render_template(template, payload) == rendered


def test_removed_templates_are_not_registered() -> None:
    with pytest.raises(ValueError, match="unknown email template: decision_warn"):
        render_template("decision_warn", {})
    with pytest.raises(ValueError, match="unknown email template: policy_gap_detected"):
        render_template("policy_gap_detected", {})
