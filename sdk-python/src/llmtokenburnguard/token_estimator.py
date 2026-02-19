# Local input token estimation helpers for protect preflight.
from __future__ import annotations

from typing import Any

import tiktoken

_ENCODER_CACHE: dict[str, Any] = {}
_DEFAULT_ENCODING = "cl100k_base"


def estimate_input_tokens(payload: dict[str, Any]) -> int | None:
    # Return a best-effort local token count for supported request shapes.
    text = _extract_text(payload)
    if text is None:
        return None
    try:
        encoder = _get_encoder(payload.get("model") if isinstance(payload.get("model"), str) else None)
        return len(encoder.encode(text))
    except Exception:
        return None


def _extract_text(payload: dict[str, Any]) -> str | None:
    messages = payload.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
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
    key = model or _DEFAULT_ENCODING
    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached
    if model is not None:
        try:
            encoder = tiktoken.encoding_for_model(model)
        except Exception:
            encoder = tiktoken.get_encoding(_DEFAULT_ENCODING)
    else:
        encoder = tiktoken.get_encoding(_DEFAULT_ENCODING)
    _ENCODER_CACHE[key] = encoder
    return encoder
