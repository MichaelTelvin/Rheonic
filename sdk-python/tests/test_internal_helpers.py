from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from rheonic import token_estimator as te
from rheonic.providers import anthropic_adapter as anthropic
from rheonic.providers import google_adapter as google
from rheonic.providers import openai_adapter as openai


def test_extract_text_supports_messages_and_prompt_shapes() -> None:
    message_text = te._extract_text({"messages": [{"content": "hello"}, {"content": [{"text": "world"}]}]})
    assert isinstance(message_text, str)
    assert '"content":"hello"' in message_text
    assert '"text":"world"' in message_text
    assert te._extract_text({"prompt": "prompt-body"}) == "prompt-body"


def test_estimate_input_tokens_counts_full_tool_message_payload() -> None:
    tool_payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "content": "done",
            }
        ],
    }
    text_only_payload = {"model": "gpt-4o-mini", "prompt": "done"}

    tool_estimate = te.estimate_input_tokens(tool_payload)
    text_only_estimate = te.estimate_input_tokens(text_only_payload)

    assert isinstance(tool_estimate, int)
    assert isinstance(text_only_estimate, int)
    assert tool_estimate > text_only_estimate


def test_extract_text_falls_back_to_text_only_when_json_serialization_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(te.json, "dumps", lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("boom")))
    rendered = te._extract_text({"messages": [{"content": "hello"}, {"content": [{"text": "world"}]}]})
    assert rendered == "hello\nworld"


@pytest.mark.parametrize(
    ("payload",),
    [
        ({"messages": ["bad"]},),
        ({"messages": [{"content": [123]}]},),
        ({"messages": [{"content": 123}]},),
    ],
)
def test_extract_text_fallback_returns_none_for_invalid_message_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    monkeypatch.setattr(te.json, "dumps", lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("boom")))
    assert te._extract_text(payload) is None


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        ({"messages": ["bad"]}, '"bad"'),
        ({"messages": [{"content": [123]}]}, "[123]"),
        ({"messages": [{"content": 123}]}, '"content":123'),
    ],
)
def test_extract_text_serializes_non_text_message_shapes(payload: dict[str, Any], expected_fragment: str) -> None:
    rendered = te._extract_text(payload)
    assert isinstance(rendered, str)
    assert expected_fragment in rendered


def test_get_encoder_handles_missing_tiktoken_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(te, "tiktoken", None)
    monkeypatch.setattr(te, "_ENCODER_CACHE", {})
    assert te._get_encoder("gpt-4o-mini") is None

    calls: list[tuple[str, str]] = []

    class FakeTiktoken:
        @staticmethod
        def encoding_for_model(model: str) -> object:
            calls.append(("model", model))
            return object()

        @staticmethod
        def get_encoding(name: str) -> object:
            calls.append(("encoding", name))
            return object()

    monkeypatch.setattr(te, "tiktoken", FakeTiktoken)
    monkeypatch.setattr(te, "_ENCODER_CACHE", {})
    first = te._get_encoder("gpt-4o-mini")
    second = te._get_encoder("gpt-4o-mini")
    assert first is second
    assert calls == [("model", "gpt-4o-mini")]


def test_get_encoder_falls_back_to_default_encoding_when_model_lookup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeTiktoken:
        @staticmethod
        def encoding_for_model(model: str) -> object:
            calls.append(("model", model))
            raise KeyError(model)

        @staticmethod
        def get_encoding(name: str) -> object:
            calls.append(("encoding", name))
            return {"encoding": name}

    monkeypatch.setattr(te, "tiktoken", FakeTiktoken)
    monkeypatch.setattr(te, "_ENCODER_CACHE", {})
    encoder = te._get_encoder("unknown-model")
    assert encoder == {"encoding": te.sdk_config.default_tokenizer_encoding}
    assert calls == [("model", "unknown-model"), ("encoding", te.sdk_config.default_tokenizer_encoding)]


def test_estimate_by_chars_honors_minimum_token_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        te,
        "sdk_config",
        SimpleNamespace(
            default_tokenizer_encoding=te.sdk_config.default_tokenizer_encoding,
            token_estimate_chars_per_token=0,
        ),
    )
    assert te._estimate_by_chars("") == 0
    assert te._estimate_by_chars("abcd") == 4


def test_estimate_input_tokens_falls_back_to_char_estimate_on_encoder_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadEncoder:
        def encode(self, _text: str) -> list[int]:
            raise RuntimeError("boom")

    monkeypatch.setattr(te, "_get_encoder", lambda _model: BadEncoder())
    monkeypatch.setattr(te, "_estimate_by_chars", lambda text: len(text) + 1)
    assert te.estimate_input_tokens({"prompt": "abc"}) == 4


def test_estimate_input_tokens_returns_none_without_supported_prompt_or_messages() -> None:
    assert te.estimate_input_tokens({"model": "gpt-4o-mini"}) is None


def test_estimate_input_tokens_uses_capped_char_fallback_when_encoder_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(te, "_get_encoder", lambda _model: None)
    monkeypatch.setattr(te, "_estimate_by_chars", lambda _text: te.sdk_config.max_input_token_estimate + 100)
    assert te.estimate_input_tokens({"prompt": "abc"}) == te.sdk_config.max_input_token_estimate


def test_prewarm_token_estimator_swallows_encoder_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(te, "_get_encoder", lambda _model: (_ for _ in ()).throw(RuntimeError("boom")))
    te.prewarm_token_estimator("gpt-4o-mini")


def test_openai_extractors_cover_status_and_output_shapes() -> None:
    assert openai._extract_http_status(SimpleNamespace(status_code=429)) == 429
    assert openai._extract_http_status(SimpleNamespace(status=503)) == 503
    assert openai._extract_http_status(SimpleNamespace(response=SimpleNamespace(status_code=418))) == 418
    assert openai._extract_http_status(RuntimeError("boom")) is None

    assert openai._extract_input_tokens_estimate((), {"input_tokens": 5}) == 5
    assert openai._extract_input_tokens_estimate(({"input_tokens": 7},), {}) == 7
    assert openai._extract_input_tokens_estimate((), {}) is None

    assert openai._extract_max_output_tokens((), {"max_tokens": 8}) == 8
    assert openai._extract_max_output_tokens((), {"max_output_tokens": 9}) == 9
    assert openai._extract_max_output_tokens(({"max_tokens": 10},), {}) == 10
    assert openai._extract_max_output_tokens(({"max_output_tokens": 11},), {}) == 11
    assert openai._extract_max_output_tokens((), {}) is None


def test_openai_estimator_handles_override_explicit_and_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    openai._set_token_estimator_for_tests(lambda _payload: "bad")
    assert openai._estimate_input_tokens({"prompt": "hello"}) is None
    openai._set_token_estimator_for_tests(None)

    assert openai._estimate_input_tokens({"input_tokens": 12}) == 12

    monkeypatch.setattr(openai, "estimate_input_tokens", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")))
    assert openai._estimate_input_tokens({"prompt": "hello"}) is None


def test_openai_apply_clamp_handles_payload_and_default_insertion_paths() -> None:
    unchanged = openai._apply_openai_clamp((), {}, {"decision": "allow"})
    assert unchanged == ((), {})

    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 16, "applied": False},
    }
    args, kwargs = openai._apply_openai_clamp(({"model": "gpt-4o-mini"},), {}, decision)
    assert args[0]["max_tokens"] == 16
    assert kwargs == {}
    assert decision["clamp"]["applied"] is True

    second_decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 20, "applied": False},
    }
    _, second_kwargs = openai._apply_openai_clamp((), {}, second_decision)
    assert second_kwargs["max_tokens"] == 20
    assert second_decision["clamp"]["applied"] is True


def test_openai_mark_clamp_only_marks_when_reduced() -> None:
    decision = {"clamp": {"applied": False}}
    openai._mark_clamp_applied_if_changed(decision, 100, 100)
    assert decision["clamp"]["applied"] is False
    openai._mark_clamp_applied_if_changed(decision, None, 100)
    assert decision["clamp"]["applied"] is True


def test_google_extractors_cover_request_payload_and_usage_shapes() -> None:
    assert google._extract_requested_model(SimpleNamespace(model="gemini-1.5-pro"), (), {}) == "gemini-1.5-pro"
    assert google._extract_requested_model(SimpleNamespace(model_name="gemini-1.5-flash"), (), {}) == "gemini-1.5-flash"
    assert google._extract_requested_model(SimpleNamespace(), ({"model": "from-args"},), {}) == "from-args"

    assert google._extract_request_payload("gemini", ("prompt",), {}) == {"model": "gemini", "prompt": "prompt"}
    assert google._extract_request_payload("gemini", ({"contents": "x"},), {}) == {"contents": "x", "model": "gemini"}
    assert google._extract_request_payload("gemini", (), {"temperature": 0.1}) == {
        "temperature": 0.1,
        "model": "gemini",
    }

    assert google._extract_max_output_tokens((), {"generation_config": {"max_output_tokens": 12}}) == 12
    assert google._extract_max_output_tokens(({"generation_config": {"max_output_tokens": 13}},), {}) == 13
    assert google._extract_max_output_tokens((), {}) is None

    assert google._extract_total_tokens(SimpleNamespace(usage_metadata=SimpleNamespace(total_token_count=8))) == 8
    assert (
        google._extract_total_tokens(
            SimpleNamespace(
                response=SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=3, candidates_token_count=5))
            )
        )
        == 8
    )
    assert google._extract_total_tokens(SimpleNamespace()) is None


def test_google_apply_clamp_covers_kwargs_args_and_default_paths() -> None:
    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 32, "applied": False},
    }
    _, kwargs = google._apply_google_clamp((), {"generation_config": {"max_output_tokens": 64}}, decision)
    assert kwargs["generation_config"]["max_output_tokens"] == 32
    assert decision["clamp"]["applied"] is True

    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 21, "applied": False},
    }
    args, kwargs = google._apply_google_clamp(({"prompt": "hi"},), {}, decision)
    assert args[0]["generation_config"]["max_output_tokens"] == 21
    assert kwargs == {}

    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 11, "applied": False},
    }
    _, kwargs = google._apply_google_clamp((), {}, decision)
    assert kwargs["generation_config"]["max_output_tokens"] == 11


def test_google_estimator_and_status_helpers_cover_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    google._set_token_estimator_for_tests(lambda _payload: "bad")
    assert google._estimate_input_tokens({"prompt": "hello"}) is None
    google._set_token_estimator_for_tests(None)
    assert google._estimate_input_tokens({"input_tokens": 7}) == 7
    monkeypatch.setattr(google, "estimate_input_tokens", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")))
    assert google._estimate_input_tokens({"prompt": "hello"}) is None

    assert google._extract_http_status(SimpleNamespace(status_code=500)) == 500
    assert google._extract_http_status(SimpleNamespace(status=502)) == 502
    assert google._extract_http_status(SimpleNamespace(response=SimpleNamespace(status_code=504))) == 504
    assert google._extract_http_status(RuntimeError("boom")) is None


def test_anthropic_extractors_and_estimator_cover_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    assert anthropic._extract_request_payload(({"model": "claude"},), {}) == {"model": "claude"}
    assert anthropic._extract_request_payload((), {"model": "claude"}) == {"model": "claude"}
    assert anthropic._extract_requested_model((), {"model": "claude"}) == "claude"
    assert anthropic._extract_requested_model(({"model": "claude-arg"},), {}) == "claude-arg"
    assert anthropic._extract_requested_model((), {}) is None
    assert anthropic._extract_max_output_tokens((), {"max_tokens": 9}) == 9
    assert anthropic._extract_max_output_tokens(({"max_tokens": 10},), {}) == 10
    assert anthropic._extract_max_output_tokens((), {}) is None

    anthropic._set_token_estimator_for_tests(lambda _payload: "bad")
    assert anthropic._estimate_input_tokens({"prompt": "hello"}) is None
    anthropic._set_token_estimator_for_tests(None)
    assert anthropic._estimate_input_tokens({"input_tokens": 6}) == 6
    monkeypatch.setattr(
        anthropic, "estimate_input_tokens", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert anthropic._estimate_input_tokens({"prompt": "hello"}) is None


def test_anthropic_status_and_clamp_helpers_cover_remaining_paths() -> None:
    assert anthropic._extract_http_status(SimpleNamespace(status_code=429)) == 429
    assert anthropic._extract_http_status(SimpleNamespace(status=430)) == 430
    assert anthropic._extract_http_status(SimpleNamespace(response=SimpleNamespace(status_code=431))) == 431
    assert anthropic._extract_http_status(RuntimeError("boom")) is None

    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 12, "applied": False},
    }
    _, kwargs = anthropic._apply_anthropic_clamp((), {"max_tokens": 18}, decision)
    assert kwargs["max_tokens"] == 12
    assert decision["clamp"]["applied"] is True

    decision = {
        "decision": "clamp",
        "reason": "token_clamp",
        "apply_clamp_enabled": True,
        "clamp": {"recommended_max_output_tokens": 14, "applied": False},
    }
    args, kwargs = anthropic._apply_anthropic_clamp(({"model": "claude"},), {}, decision)
    assert args[0]["max_tokens"] == 14
    assert kwargs == {}

    decision = {"clamp": {"applied": False}}
    anthropic._mark_clamp_applied_if_changed(decision, 5, 5)
    assert decision["clamp"]["applied"] is False
    anthropic._mark_clamp_applied_if_changed(decision, None, 5)
    assert decision["clamp"]["applied"] is True
