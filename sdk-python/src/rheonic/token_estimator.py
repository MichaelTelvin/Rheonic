# Local input token estimation helpers for protect preflight.
from __future__ import annotations

import json
from types import ModuleType
from typing import Any

from rheonic.config import sdk_config

try:
    import tiktoken as _tiktoken
except Exception:  # pragma: no cover - import availability depends on environment
    tiktoken: ModuleType | None = None
else:
    tiktoken = _tiktoken

_ENCODER_CACHE: dict[str, Any] = {}


def prewarm_token_estimator(model: str | None = None) -> None:
    # Best-effort encoder warmup to avoid first-request tokenizer cold start.
    try:
        _get_encoder(model)
    except Exception:
        return


def estimate_input_tokens(payload: dict[str, Any]) -> int | None:
    # Return a best-effort local token count for supported request shapes.
    text = _extract_text(payload)
    if text is None:
        return None
    try:
        encoder = _get_encoder(payload.get("model") if isinstance(payload.get("model"), str) else None)
        if encoder is None:
            return min(sdk_config.max_input_token_estimate, _estimate_by_chars(text))
        return min(sdk_config.max_input_token_estimate, len(encoder.encode(text)))
    except Exception:
        return min(sdk_config.max_input_token_estimate, _estimate_by_chars(text))


def _extract_text(payload: dict[str, Any]) -> str | None:
    messages = payload.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        try:
            return json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            for message in messages:
                if not isinstance(message, dict):
                    return None
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(content)
                    continue
                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            return None
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                    continue
                return None
            return "\n".join(parts)

    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return prompt
    return None


def _get_encoder(model: str | None) -> Any:
    if tiktoken is None:
        return None
    key = model or sdk_config.default_tokenizer_encoding
    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached
    if model is not None:
        try:
            encoder = tiktoken.encoding_for_model(model)
        except Exception:
            encoder = tiktoken.get_encoding(sdk_config.default_tokenizer_encoding)
    else:
        encoder = tiktoken.get_encoding(sdk_config.default_tokenizer_encoding)
    _ENCODER_CACHE[key] = encoder
    return encoder


def _estimate_by_chars(text: str) -> int:
    if not text:
        return 0
    chars_per_token = max(int(sdk_config.token_estimate_chars_per_token), 1)
    return max(1, len(text) // chars_per_token + (1 if len(text) % chars_per_token else 0))
