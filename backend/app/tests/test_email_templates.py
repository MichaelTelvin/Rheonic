import pytest

from app.application.email_templates.base_layout import (
    format_evidence,
    format_page_location,
    format_timestamp,
    humanize_incident_type,
)
from app.application.email_templates.registry import render_template


def test_format_timestamp_renders_human_readable_utc() -> None:
    assert format_timestamp("2026-03-05T10:00:00Z") == "Mar 05, 2026 10:00 UTC"
    assert format_timestamp("2026-03-05T10:00:00+00:00") == "Mar 05, 2026 10:00 UTC"
    assert format_timestamp("") == "-"
    assert format_timestamp(None) == "-"


def test_email_template_helpers_render_human_readable_values() -> None:
    assert humanize_incident_type("retry_storm") == "Retry storm"
    assert humanize_incident_type("block") == "Block"
    assert format_page_location("/app/alerts") == "Dashboard / Alerts"
    evidence_copy = format_evidence(
        {
            "count": 1,
            "provider": "openai",
            "last_seen_at": "2026-03-15T18:28:46.668971+00:00",
        }
    )
    assert "Count: 1" in evidence_copy
    assert "Provider: openai" in evidence_copy
    assert "Last Seen At: Mar 15, 2026 18:28 UTC" in evidence_copy


def test_feedback_template_snapshot_is_deterministic() -> None:
    payload = {
        "report_type": "bug",
        "message": "Need dark mode",
        "email": "u@example.com",
        "user_id": "u1",
        "user_email": "u@example.com",
        "project_id": "p1",
        "page": "/app/alerts",
        "mode": "protect",
        "timestamp": "2026-03-05T10:00:00Z",
        "app_version": "1.2.3",
    }
    rendered = render_template("feedback_submitted", payload)
    assert rendered["subject"] == "Rheonic beta bug report"
    assert "Rheonic beta bug report" in rendered["html"]
    assert "New product report received." in rendered["html"]
    assert ">System<" not in rendered["html"]
    assert "/assets/logo/logo-48.png" in rendered["html"]
    assert "Report Type: Bug report" in rendered["text"]
    assert "Page: Dashboard / Alerts" in rendered["text"]
    assert "Mar 05, 2026 10:00 UTC" in rendered["html"]
    assert "Timestamp: Mar 05, 2026 10:00 UTC" in rendered["text"]
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
                "model": "claude-3.7-sonnet",
                "environment": "prod",
                "evidence": {"failure_count": 5, "window_seconds": 60},
                "created_at": "2026-03-05T10:00:00Z",
                "last_seen_at": "2026-03-05T10:01:10Z",
                "sent_at": "2026-03-05T10:01:10Z",
            },
            "[Rheonic] Incident opened: Retry storm (p1)",
            "Incident opened",
            "Incident Type: Retry storm",
        ),
        (
            "protection_block",
            {
                "project_id": "p2",
                "provider": "google",
                "model": "gemini-1.5-pro",
                "environment": "prod",
                "reason": "tok_cap_breach",
                "detail_reason": "tok_cap_breach",
                "requests_60s": 2,
                "tokens_60s": 2000,
                "req_cap": 100,
                "tok_cap": 1500,
                "blocked_until": "2026-03-05T10:01:00Z",
                "retry_after_seconds": 60,
                "source": "live",
                "sent_at": "2026-03-05T10:00:00Z",
            },
            "[Rheonic] Protect alert: Token cap exceeded (p2)",
            "Blocked traffic",
            "Action: Blocked",
        ),
        (
            "incident_block",
            {
                "project_id": "p2",
                "incident_id": "inc-block",
                "incident_type": "block",
                "provider": "google",
                "model": "gemini-1.5-pro",
                "environment": "prod",
                "created_at": "2026-03-05T10:00:00Z",
                "last_seen_at": "2026-03-05T10:00:30Z",
                "evidence": {"reason": "tok_cap_breach", "tokens_60s": 2000, "tok_cap": 1500},
                "sent_at": "2026-03-05T10:00:00Z",
            },
            "[Rheonic] Incident opened: Block (p2)",
            "Protect block incident opened",
            "Incident Type: Block",
        ),
        (
            "protection_clamp_started",
            {
                "project_id": "p2",
                "provider": "google",
                "model": "gemini-1.5-pro",
                "environment": "prod",
                "reason": "token_clamp",
                "requests_60s": 95,
                "tokens_60s": 1600,
                "req_cap": 100,
                "tok_cap": 1700,
                "estimated_next_tokens": 120,
                "clamp": {"recommended_max_output_tokens": 32},
                "sent_at": "2026-03-05T10:00:00Z",
            },
            "[Rheonic] Protect alert: Clamp started - Token Clamp (p2)",
            "Clamp started",
            "Action: Clamp",
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
            "[Rheonic] Protect alert: Resolved - Loop suspect (p3)",
            "Incident resolved",
            "Resolved By: auto",
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
            "[Rheonic] Protect alert: Webhook delivery failed (p4)",
            "Webhook delivery failed",
            "Error Code: webhook_http_error",
        ),
    ]

    for template, payload, subject, expected_title, expected_text_line in cases:
        rendered = render_template(template, payload)
        assert rendered["subject"] == subject
        assert expected_title in rendered["html"]
        assert expected_text_line in rendered["text"]
        assert "RHEONIC" in rendered["html"]
        assert ">Protect alert<" not in rendered["html"]
        assert "UTC" in rendered["text"]
        assert render_template(template, payload) == rendered


def test_fail_closed_protection_block_omits_blank_rows() -> None:
    rendered = render_template(
        "protection_block",
        {
            "project_id": "p-fail",
            "provider": "openai",
            "environment": "staging",
            "reason": "fail_closed",
            "detail_reason": "decision_timeout",
            "source": "timeout_fallback",
            "sent_at": "2026-03-05T10:00:00Z",
        },
    )
    assert "Requests / 60s" not in rendered["text"]
    assert "Tokens / 60s" not in rendered["text"]
    assert "Request cap" not in rendered["text"]
    assert "Token cap" not in rendered["text"]
    assert "Blocked Until" not in rendered["text"]
    assert "Retry After" not in rendered["text"]
    assert "Detail Reason: Decision timeout" in rendered["text"]
    assert "Source: Timeout fallback" in rendered["text"]


def test_fail_closed_protection_block_includes_metrics_when_present() -> None:
    rendered = render_template(
        "protection_block",
        {
            "project_id": "p-fail",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "environment": "staging",
            "reason": "fail_closed",
            "detail_reason": "decision_timeout",
            "requests_60s": 12,
            "tokens_60s": 1440,
            "req_cap": 500,
            "tok_cap": 1750,
            "source": "timeout_fallback",
            "sent_at": "2026-03-05T10:00:00Z",
        },
    )
    assert "Requests / 60s: 12" in rendered["text"]
    assert "Tokens / 60s: 1440" in rendered["text"]
    assert "Request Cap: 500" in rendered["text"]
    assert "Token Cap: 1750" in rendered["text"]


def test_removed_templates_are_not_registered() -> None:
    with pytest.raises(ValueError, match="unknown email template: decision_warn"):
        render_template("decision_warn", {})
    with pytest.raises(ValueError, match="unknown email template: policy_gap_detected"):
        render_template("policy_gap_detected", {})
