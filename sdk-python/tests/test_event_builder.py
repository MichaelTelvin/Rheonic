# Unit tests for SDK event builder.
import pytest
from rheonic import event_builder as event_builder_module
from rheonic.event_builder import EventBuilder, build_event


def test_build_event_schema_excludes_project_id() -> None:
    # Event payload should match backend schema and omit project_id.
    payload = build_event(
        provider="openai",
        model="gpt-4o-mini",
        environment="dev",
        request={"endpoint": "/chat", "input_tokens": 3, "token_explosion_tokens": 5},
        response={"total_tokens": 10, "latency_ms": 42, "http_status": 200},
    )

    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["environment"] == "dev"
    assert "project_id" not in payload
    assert isinstance(payload["request"], dict)
    assert isinstance(payload["response"], dict)
    assert payload["request"]["token_explosion_tokens"] == 5


def test_event_builder_normalizes_optional_fields() -> None:
    payload = EventBuilder().build(
        {
            "provider": "openai",
            "model": 123,
            "request": "bad",
            "response": "bad",
            "ts": 42,
        }
    )

    assert payload["provider"] == "openai"
    assert payload["model"] is None
    assert payload["environment"] == "dev"
    assert payload["request"] == {}
    assert payload["response"] == {}


def test_event_builder_reraises_and_logs_when_build_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        event_builder_module, "build_event", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    logged: list[str] = []
    monkeypatch.setattr(event_builder_module.logger, "exception", lambda message: logged.append(message))

    with pytest.raises(RuntimeError, match="boom"):
        EventBuilder().build({"provider": "openai"})

    assert logged == ["Event builder failed"]
