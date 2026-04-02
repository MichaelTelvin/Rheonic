# Event builder helpers.
from datetime import datetime, timezone
from typing import Any, cast

from rheonic.logger import get_logger
from rheonic.protect_engine import RHEONICValidationError

logger = get_logger(__name__)

_PUBLIC_EVENT_KEYS = {"provider", "model", "environment", "ts", "status", "request", "response"}
_INTERNAL_EVENT_KEYS = {
    "ts",
    "provider",
    "requested_model",
    "resolved_model",
    "environment",
    "status",
    "request",
    "response",
}
_REQUEST_KEYS = {
    "endpoint",
    "feature",
    "request_fingerprint",
    "input_tokens",
    "input_tokens_estimate",
    "token_explosion_tokens",
    "max_output_tokens",
    "protect_decision",
    "protect_reason",
}
_RESPONSE_KEYS = {"http_status", "latency_ms", "total_tokens", "output_tokens", "error_type", "error_message"}


def _fail_validation(message: str) -> None:
    raise RHEONICValidationError(message)


def _validate_mapping(value: dict[str, Any] | None, allowed_keys: set[str], label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _fail_validation(f"RHEONIC: {label} must be an object.")
    extra_keys = set(value) - allowed_keys
    if extra_keys:
        _fail_validation(f"RHEONIC: unexpected {label} property: {sorted(extra_keys)[0]}")
    return value


def _validate_optional_string(value: Any, label: str) -> None:
    if value is not None and not isinstance(value, str):
        _fail_validation(f"RHEONIC: {label} must be a string.")


def _validate_optional_number(value: Any, label: str) -> None:
    if value is not None and not isinstance(value, int):
        _fail_validation(f"RHEONIC: {label} must be a number.")


def _validate_request(request: dict[str, Any] | None) -> dict[str, Any]:
    request_map = _validate_mapping(request, _REQUEST_KEYS, "event.request")
    _validate_optional_string(request_map.get("endpoint"), "event.request.endpoint")
    _validate_optional_string(request_map.get("feature"), "event.request.feature")
    _validate_optional_string(request_map.get("request_fingerprint"), "event.request.request_fingerprint")
    _validate_optional_number(request_map.get("input_tokens"), "event.request.input_tokens")
    _validate_optional_number(request_map.get("input_tokens_estimate"), "event.request.input_tokens_estimate")
    _validate_optional_number(request_map.get("token_explosion_tokens"), "event.request.token_explosion_tokens")
    _validate_optional_number(request_map.get("max_output_tokens"), "event.request.max_output_tokens")
    _validate_optional_string(request_map.get("protect_decision"), "event.request.protect_decision")
    _validate_optional_string(request_map.get("protect_reason"), "event.request.protect_reason")
    return request_map


def _validate_response(response: dict[str, Any] | None) -> dict[str, Any]:
    response_map = _validate_mapping(response, _RESPONSE_KEYS, "event.response")
    _validate_optional_number(response_map.get("http_status"), "event.response.http_status")
    _validate_optional_number(response_map.get("latency_ms"), "event.response.latency_ms")
    _validate_optional_number(response_map.get("total_tokens"), "event.response.total_tokens")
    _validate_optional_number(response_map.get("output_tokens"), "event.response.output_tokens")
    _validate_optional_string(response_map.get("error_type"), "event.response.error_type")
    _validate_optional_string(response_map.get("error_message"), "event.response.error_message")
    return response_map


def build_event(
    provider: str,
    model: str | None = None,
    environment: str = "dev",
    status: str | None = None,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    # Build backend ingest payload without project_id.
    if not isinstance(provider, str) or not provider.strip():
        _fail_validation("RHEONIC: event.provider must be a non-empty string.")
    _validate_optional_string(model, "event.model")
    _validate_optional_string(environment, "event.environment")
    _validate_optional_string(status, "event.status")
    _validate_optional_string(ts, "event.ts")
    return {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "requested_model": model,
        "resolved_model": None,
        "environment": environment,
        **({"status": status} if status is not None else {}),
        "request": _validate_request(request),
        "response": _validate_response(response),
    }


def build_internal_event(
    provider: str,
    requested_model: str | None = None,
    resolved_model: str | None = None,
    environment: str = "dev",
    status: str | None = None,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    if not isinstance(provider, str) or not provider.strip():
        _fail_validation("RHEONIC: event.provider must be a non-empty string.")
    _validate_optional_string(requested_model, "event.requested_model")
    _validate_optional_string(resolved_model, "event.resolved_model")
    _validate_optional_string(environment, "event.environment")
    _validate_optional_string(status, "event.status")
    _validate_optional_string(ts, "event.ts")
    return {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "environment": environment,
        **({"status": status} if status is not None else {}),
        "request": _validate_request(request),
        "response": _validate_response(response),
    }


def normalize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _fail_validation("RHEONIC: event must be an object.")

    payload_keys = set(payload)
    if {"requested_model", "resolved_model"} & payload_keys:
        extra_keys = payload_keys - _INTERNAL_EVENT_KEYS
        if extra_keys:
            _fail_validation(f"RHEONIC: unexpected event property: {sorted(extra_keys)[0]}")
        missing_keys = [
            key
            for key in ("ts", "provider", "requested_model", "resolved_model", "environment", "request", "response")
            if key not in payload
        ]
        if missing_keys:
            _fail_validation(f"RHEONIC: event.{missing_keys[0]} is required.")
        ts_value = payload.get("ts")
        provider_value = payload.get("provider")
        requested_model = payload.get("requested_model")
        resolved_model = payload.get("resolved_model")
        environment_value = payload.get("environment")
        if not isinstance(ts_value, str) or not ts_value.strip():
            _fail_validation("RHEONIC: event.ts must be a non-empty string.")
        if not isinstance(provider_value, str) or not provider_value.strip():
            _fail_validation("RHEONIC: event.provider must be a non-empty string.")
        if not isinstance(environment_value, str) or not environment_value.strip():
            _fail_validation("RHEONIC: event.environment must be a non-empty string.")
        _validate_optional_string(payload.get("status"), "event.status")
        internal_ts = cast(str, ts_value)
        internal_provider = cast(str, provider_value)
        internal_environment = cast(str, environment_value)
        return build_internal_event(
            provider=internal_provider,
            requested_model=requested_model if isinstance(requested_model, str) else None,
            resolved_model=resolved_model if isinstance(resolved_model, str) else None,
            environment=internal_environment,
            status=payload.get("status") if isinstance(payload.get("status"), str) else None,
            request=payload.get("request") if isinstance(payload.get("request"), dict) else None,
            response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
            ts=internal_ts,
        )

    extra_keys = payload_keys - _PUBLIC_EVENT_KEYS
    if extra_keys:
        _fail_validation(f"RHEONIC: unexpected event property: {sorted(extra_keys)[0]}")
    provider_value = payload.get("provider")
    environment_value = payload.get("environment", "dev")
    if not isinstance(provider_value, str) or not provider_value.strip():
        _fail_validation("RHEONIC: event.provider must be a non-empty string.")
    if not isinstance(environment_value, str) or not environment_value.strip():
        _fail_validation("RHEONIC: event.environment must be a non-empty string.")
    _validate_optional_string(payload.get("status"), "event.status")
    public_provider = cast(str, provider_value)
    public_environment = cast(str, environment_value)
    return build_event(
        provider=public_provider,
        model=payload.get("model"),
        environment=public_environment,
        status=payload.get("status") if isinstance(payload.get("status"), str) else None,
        request=payload.get("request") if isinstance(payload.get("request"), dict) else None,
        response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
        ts=payload.get("ts") if isinstance(payload.get("ts"), str) else None,
    )


class EventBuilder:
    # Builds normalized usage events from provider responses.

    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Build a backend-compatible event payload.
        try:
            return build_event(
                provider=str(payload.get("provider", "unknown")),
                model=payload.get("model") if isinstance(payload.get("model"), str) else None,
                environment=str(payload.get("environment", "dev")),
                status=payload.get("status") if isinstance(payload.get("status"), str) else None,
                request=payload.get("request") if isinstance(payload.get("request"), dict) else None,
                response=payload.get("response") if isinstance(payload.get("response"), dict) else None,
                ts=payload.get("ts") if isinstance(payload.get("ts"), str) else None,
            )
        except Exception:
            logger.exception("Event builder failed")
            raise
