from __future__ import annotations

import json
import re
from typing import Any


_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_FORBIDDEN_KEYS = {"__proto__", "constructor", "prototype"}
_MAX_TEMPLATE_LENGTH = 8192


def normalize_payload_template_json(raw: str | None) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) > _MAX_TEMPLATE_LENGTH:
        raise ValueError("payload template is too large")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("payload template must be valid JSON") from exc
    _validate_template_node(parsed)
    if not isinstance(parsed, dict):
        raise ValueError("payload template root must be an object")
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def parse_payload_template_json(raw: str | None) -> dict[str, Any] | None:
    normalized = normalize_payload_template_json(raw)
    if normalized is None:
        return None
    parsed = json.loads(normalized)
    if not isinstance(parsed, dict):
        raise ValueError("payload template root must be an object")
    return parsed


def render_payload_template(*, template: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    rendered = _render_node(template, context)
    if not isinstance(rendered, dict):
        raise ValueError("rendered payload template root must be an object")
    return rendered


def _validate_template_node(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise ValueError("payload template keys must be strings")
            if key in _FORBIDDEN_KEYS:
                raise ValueError(f"payload template contains forbidden key: {key}")
            _validate_template_node(value)
        return
    if isinstance(node, list):
        for item in node:
            _validate_template_node(item)
        return
    if isinstance(node, (str, int, float, bool)) or node is None:
        return
    raise ValueError("payload template contains unsupported values")


def _render_node(node: Any, context: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {key: _render_node(value, context) for key, value in node.items()}
    if isinstance(node, list):
        return [_render_node(item, context) for item in node]
    if isinstance(node, str):
        return _render_string(node, context)
    return node


def _render_string(value: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        resolved = context.get(token)
        return "" if resolved is None else str(resolved)

    return _PLACEHOLDER_PATTERN.sub(replace, value)
