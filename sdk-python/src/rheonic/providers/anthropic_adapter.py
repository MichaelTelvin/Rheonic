# Anthropic instrumentation wrapper.
import inspect
from time import perf_counter
from typing import Any

from rheonic.client import Client, get_default_client
from rheonic.event_builder import build_event
from rheonic.logger import get_logger
from rheonic.protect_engine import RHEONICBlockedError
from rheonic.provider_model_validation import validate_provider_model
from rheonic.token_estimator import estimate_input_tokens

logger = get_logger(__name__)

_token_estimator_override_for_tests: Any | None = None


def _set_token_estimator_for_tests(estimator: Any | None) -> None:
    # Test hook to override token estimator behavior deterministically.
    global _token_estimator_override_for_tests
    _token_estimator_override_for_tests = estimator


def instrument_anthropic(
    anthropic_client: Any,
    client: Client | None = None,
    environment: str | None = None,
    endpoint: str | None = None,
    feature: str | None = None,
) -> Any:
    # Instrument messages.create and emit usage events.
    resolved_client = client or get_default_client()
    if resolved_client is None:
        return anthropic_client

    messages = getattr(anthropic_client, "messages", None)
    original_create = getattr(messages, "create", None)
    if messages is None or not callable(original_create):
        return anthropic_client

    if inspect.iscoroutinefunction(original_create):

        async def wrapped_create_async(*args: Any, **kwargs: Any) -> Any:
            started_at = perf_counter()
            request_payload = _extract_request_payload(args, kwargs)
            requested_model = _extract_requested_model(args, kwargs)
            validate_provider_model("anthropic", requested_model)
            token_estimate_started_at = perf_counter()
            estimated_input_tokens = _estimate_input_tokens(request_payload)
            resolved_client.debug_log(
                "Protect token estimation completed",
                provider="anthropic",
                model=requested_model,
                latency_ms=int((perf_counter() - token_estimate_started_at) * 1000),
                estimated_input_tokens=estimated_input_tokens,
            )
            protect_decision = _preflight(
                sdk_client=resolved_client,
                requested_model=requested_model,
                estimated_input_tokens=estimated_input_tokens,
                max_output_tokens=_extract_max_output_tokens(args, kwargs),
                environment=environment or resolved_client.environment,
                feature=feature,
            )
            if protect_decision.get("decision") == "block":
                raise RHEONICBlockedError(str(protect_decision.get("reason") or "blocked"))
            call_args, call_kwargs = _apply_anthropic_clamp(args, kwargs, protect_decision)
            try:
                response = await original_create(*call_args, **call_kwargs)
                _capture_success(
                    sdk_client=resolved_client,
                    response=response,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    requested_model=requested_model,
                    estimated_input_tokens=estimated_input_tokens,
                    environment=environment,
                    endpoint=endpoint,
                    feature=feature,
                    protect_decision=str(protect_decision.get("decision") or "allow"),
                    protect_reason=str(protect_decision.get("reason") or "ok"),
                )
                return response
            except Exception as exc:
                _capture_failure(
                    sdk_client=resolved_client,
                    exc=exc,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    requested_model=requested_model,
                    estimated_input_tokens=estimated_input_tokens,
                    environment=environment,
                    endpoint=endpoint,
                    feature=feature,
                    protect_decision=str(protect_decision.get("decision") or "allow"),
                    protect_reason=str(protect_decision.get("reason") or "ok"),
                )
                raise

        messages.create = wrapped_create_async
        return anthropic_client

    def wrapped_create(*args: Any, **kwargs: Any) -> Any:
        started_at = perf_counter()
        request_payload = _extract_request_payload(args, kwargs)
        requested_model = _extract_requested_model(args, kwargs)
        validate_provider_model("anthropic", requested_model)
        token_estimate_started_at = perf_counter()
        estimated_input_tokens = _estimate_input_tokens(request_payload)
        resolved_client.debug_log(
            "Protect token estimation completed",
            provider="anthropic",
            model=requested_model,
            latency_ms=int((perf_counter() - token_estimate_started_at) * 1000),
            estimated_input_tokens=estimated_input_tokens,
        )
        protect_decision = _preflight(
            sdk_client=resolved_client,
            requested_model=requested_model,
            estimated_input_tokens=estimated_input_tokens,
            max_output_tokens=_extract_max_output_tokens(args, kwargs),
            environment=environment or resolved_client.environment,
            feature=feature,
        )
        if protect_decision.get("decision") == "block":
            raise RHEONICBlockedError(str(protect_decision.get("reason") or "blocked"))
        call_args, call_kwargs = _apply_anthropic_clamp(args, kwargs, protect_decision)
        try:
            response = original_create(*call_args, **call_kwargs)
            _capture_success(
                sdk_client=resolved_client,
                response=response,
                latency_ms=int((perf_counter() - started_at) * 1000),
                requested_model=requested_model,
                estimated_input_tokens=estimated_input_tokens,
                environment=environment,
                endpoint=endpoint,
                feature=feature,
                protect_decision=str(protect_decision.get("decision") or "allow"),
                protect_reason=str(protect_decision.get("reason") or "ok"),
            )
            return response
        except Exception as exc:
            _capture_failure(
                sdk_client=resolved_client,
                exc=exc,
                latency_ms=int((perf_counter() - started_at) * 1000),
                requested_model=requested_model,
                estimated_input_tokens=estimated_input_tokens,
                environment=environment,
                endpoint=endpoint,
                feature=feature,
                protect_decision=str(protect_decision.get("decision") or "allow"),
                protect_reason=str(protect_decision.get("reason") or "ok"),
            )
            raise

    messages.create = wrapped_create
    return anthropic_client


def _preflight(
    *,
    sdk_client: Client,
    requested_model: str | None,
    estimated_input_tokens: int | None,
    max_output_tokens: int | None,
    environment: str | None,
    feature: str | None,
) -> dict[str, object]:
    return sdk_client.preflight_protect_decision(
        {
            "provider": "anthropic",
            "model": requested_model,
            "environment": environment,
            "feature": feature,
            **({"input_tokens_estimate": estimated_input_tokens} if isinstance(estimated_input_tokens, int) else {}),
            "max_output_tokens": max_output_tokens,
        }
    )


def _capture_success(
    sdk_client: Client,
    response: Any,
    latency_ms: int,
    requested_model: str | None,
    estimated_input_tokens: int | None,
    environment: str | None,
    endpoint: str | None,
    feature: str | None,
    protect_decision: str,
    protect_reason: str,
) -> None:
    try:
        response_model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if not isinstance(total_tokens, int):
            input_tokens = getattr(usage, "input_tokens", None)
            output_tokens = getattr(usage, "output_tokens", None)
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                total_tokens = input_tokens + output_tokens
        sdk_client.capture_event(
            build_event(
                provider="anthropic",
                model=response_model if isinstance(response_model, str) else requested_model,
                environment=environment or sdk_client.environment,
                request={
                    "endpoint": endpoint,
                    "feature": feature,
                    **(
                        {"token_explosion_tokens": estimated_input_tokens}
                        if isinstance(estimated_input_tokens, int)
                        else {}
                    ),
                    "input_tokens_estimate": estimated_input_tokens
                    if isinstance(estimated_input_tokens, int)
                    else None,
                    "protect_decision": "warn" if protect_decision == "warn" else None,
                    "protect_reason": protect_reason if protect_decision == "warn" else None,
                },
                response={
                    "latency_ms": latency_ms,
                    "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
                    "http_status": 200,
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture Anthropic success event")


def _capture_failure(
    sdk_client: Client,
    exc: Exception,
    latency_ms: int,
    requested_model: str | None,
    estimated_input_tokens: int | None,
    environment: str | None,
    endpoint: str | None,
    feature: str | None,
    protect_decision: str,
    protect_reason: str,
) -> None:
    try:
        sdk_client.capture_event(
            build_event(
                provider="anthropic",
                model=requested_model,
                environment=environment or sdk_client.environment,
                request={
                    "endpoint": endpoint,
                    "feature": feature,
                    **(
                        {"token_explosion_tokens": estimated_input_tokens}
                        if isinstance(estimated_input_tokens, int)
                        else {}
                    ),
                    "input_tokens_estimate": estimated_input_tokens
                    if isinstance(estimated_input_tokens, int)
                    else None,
                    "protect_decision": "warn" if protect_decision == "warn" else None,
                    "protect_reason": protect_reason if protect_decision == "warn" else None,
                },
                response={
                    "latency_ms": latency_ms,
                    "error_type": exc.__class__.__name__ or "unknown",
                    "http_status": _extract_http_status(exc),
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture Anthropic failure event")


def _extract_request_payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if args and isinstance(args[0], dict):
        return dict(args[0])
    return dict(kwargs)


def _extract_requested_model(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    model = kwargs.get("model")
    if isinstance(model, str):
        return model
    first = args[0] if args else None
    if isinstance(first, dict):
        first_model = first.get("model")
        if isinstance(first_model, str):
            return first_model
    return None


def _extract_max_output_tokens(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    max_tokens = kwargs.get("max_tokens")
    if isinstance(max_tokens, int):
        return max_tokens
    first = args[0] if args else None
    if isinstance(first, dict):
        first_max_tokens = first.get("max_tokens")
        if isinstance(first_max_tokens, int):
            return first_max_tokens
    return None


def _estimate_input_tokens(payload: dict[str, Any]) -> int | None:
    try:
        if callable(_token_estimator_override_for_tests):
            override_value = _token_estimator_override_for_tests(payload)
            return override_value if isinstance(override_value, int) else None
        explicit = payload.get("input_tokens")
        if isinstance(explicit, int):
            return explicit
        return estimate_input_tokens(payload)
    except Exception:
        return None


def _extract_http_status(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
    return None


def _apply_anthropic_clamp(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    protect_decision: dict[str, object],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if str(protect_decision.get("decision") or "") != "warn":
        return args, kwargs
    if str(protect_decision.get("reason") or "") != "near_cap":
        return args, kwargs
    if protect_decision.get("apply_clamp_enabled") is not True:
        return args, kwargs
    clamp = protect_decision.get("clamp")
    if not isinstance(clamp, dict):
        return args, kwargs
    recommended = clamp.get("recommended_max_output_tokens")
    if not isinstance(recommended, int) or recommended < 1:
        return args, kwargs

    next_kwargs = dict(kwargs)
    next_args = list(args)
    if "max_tokens" in next_kwargs and isinstance(next_kwargs.get("max_tokens"), int):
        next_kwargs["max_tokens"] = min(int(next_kwargs["max_tokens"]), recommended)
    elif next_args and isinstance(next_args[0], dict):
        payload = dict(next_args[0])
        if isinstance(payload.get("max_tokens"), int):
            payload["max_tokens"] = min(int(payload["max_tokens"]), recommended)
        else:
            payload["max_tokens"] = recommended
        next_args[0] = payload
    else:
        next_kwargs["max_tokens"] = recommended
    _mark_clamp_applied_if_changed(
        protect_decision,
        _extract_max_output_tokens(args, kwargs),
        _extract_max_output_tokens(tuple(next_args), next_kwargs),
    )
    return tuple(next_args), next_kwargs


def _mark_clamp_applied_if_changed(
    protect_decision: dict[str, object],
    original_max_tokens: int | None,
    applied_max_tokens: int | None,
) -> None:
    clamp = protect_decision.get("clamp")
    if not isinstance(clamp, dict):
        return
    if applied_max_tokens is None:
        return
    if original_max_tokens is None or applied_max_tokens < original_max_tokens:
        clamp["applied"] = True
