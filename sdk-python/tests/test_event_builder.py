# Unit tests for SDK event builder.
from rheonic.event_builder import build_event


def test_build_event_schema_excludes_project_id() -> None:
    # Event payload should match backend schema and omit project_id.
    payload = build_event(
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        request={"endpoint": "/chat", "input_tokens": 3},
        response={"total_tokens": 10, "latency_ms": 42, "http_status": 200},
    )

    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["environment"] == "dev"
    assert "project_id" not in payload
    assert isinstance(payload["request"], dict)
    assert isinstance(payload["response"], dict)
