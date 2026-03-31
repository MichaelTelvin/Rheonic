# Google provider instrumentation wrapper.
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


def instrument_google(
    google_model: Any,
    client: Client | None = None,
    environment: str | None = None,
    endpoint: str | None = None,
    feature: str | None = None,
) -> Any:
    # Instrument generate_content and emit usage events.
    resolved_client = client or get_default_client()
    if resolved_client is None:
        return google_model

    original_generate = getattr(google_model, "generate_content", None)
    if not callable(original_generate):
        return google_model

    if inspect.iscoroutinefunction(original_generate):

        async def wrapped_generate_async(*args: Any, **kwargs: Any) -> Any:
            started_at = perf_counter()
            requested_model = _extract_requested_model(google_model, args, kwargs)
            validate_provider_model("google", requested_model)
            request_payload = _extract_request_payload(requested_model, args, kwargs)
            token_estimate_started_at = perf_counter()
            estimated_input_tokens = _estimate_input_tokens(request_payload)
            resolved_client.debug_log(
                "Protect token estimation completed",
                provider="google",
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
                raise _blocked_error_from_decision(protect_decision)
            call_args, call_kwargs = _apply_google_clamp(args, kwargs, protect_decision)
            try:
                response = await original_generate(*call_args, **call_kwargs)
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

        google_model.generate_content = wrapped_generate_async
        return google_model

    def wrapped_generate(*args: Any, **kwargs: Any) -> Any:
        started_at = perf_counter()
        requested_model = _extract_requested_model(google_model, args, kwargs)
        validate_provider_model("google", requested_model)
        request_payload = _extract_request_payload(requested_model, args, kwargs)
        token_estimate_started_at = perf_counter()
        estimated_input_tokens = _estimate_input_tokens(request_payload)
        resolved_client.debug_log(
            "Protect token estimation completed",
            provider="google",
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
            raise _blocked_error_from_decision(protect_decision)
        call_args, call_kwargs = _apply_google_clamp(args, kwargs, protect_decision)
        try:
            response = original_generate(*call_args, **call_kwargs)
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

    google_model.generate_content = wrapped_generate
    return google_model


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
            "provider": "google",
            "model": requested_model,
            "environment": environment,
            "feature": feature,
            **({"input_tokens_estimate": estimated_input_tokens} if isinstance(estimated_input_tokens, int) else {}),
            "max_output_tokens": max_output_tokens,
        }
    )


def _blocked_error_from_decision(protect_decision: dict[str, object]) -> RHEONICBlockedError:
    trace_id = protect_decision.get("trace_id")
    request_id = protect_decision.get("request_id")
    blocked_until = protect_decision.get("blocked_until")
    retry_after_seconds = protect_decision.get("retry_after_seconds")
    snapshot = protect_decision.get("snapshot")
    return RHEONICBlockedError(
        str(protect_decision.get("reason") or "blocked"),
        trace_id=str(trace_id or ""),
        request_id=str(request_id or ""),
        blocked_until=blocked_until if isinstance(blocked_until, str) else None,
        retry_after_seconds=retry_after_seconds if isinstance(retry_after_seconds, int) else None,
        snapshot=snapshot if isinstance(snapshot, dict) else None,
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
        sdk_client.capture_event(
            build_event(
                provider="google",
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
                    "protect_decision": "clamp" if protect_decision == "clamp" else None,
                    "protect_reason": protect_reason if protect_decision != "allow" else None,
                },
                response={
                    "latency_ms": latency_ms,
                    "total_tokens": _extract_total_tokens(response),
                    "http_status": 200,
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture Google success event")


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
                provider="google",
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
                    "protect_decision": "clamp" if protect_decision == "clamp" else None,
                    "protect_reason": protect_reason if protect_decision != "allow" else None,
                },
                response={
                    "latency_ms": latency_ms,
                    "error_type": exc.__class__.__name__ or "unknown",
                    "http_status": _extract_http_status(exc),
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture Google failure event")


def _extract_requested_model(google_model: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    for key in ("model", "model_name"):
        value = getattr(google_model, key, None)
        if isinstance(value, str):
            return value
    for source in (kwargs, args[0] if args and isinstance(args[0], dict) else None):
        if isinstance(source, dict):
            model = source.get("model")
            if isinstance(model, str):
                return model
    return None


def _extract_request_payload(model: str | None, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if args:
        first = args[0]
        if isinstance(first, str):
            return {"model": model, "prompt": first}
        if isinstance(first, dict):
            payload = dict(first)
            if model and "model" not in payload:
                payload["model"] = model
            return payload
    payload = dict(kwargs)
    if model and "model" not in payload:
        payload["model"] = model
    return payload


def _extract_max_output_tokens(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int | None:
    generation_config = kwargs.get("generation_config")
    if isinstance(generation_config, dict):
        max_out = generation_config.get("max_output_tokens")
        if isinstance(max_out, int):
            return max_out
    first = args[0] if args else None
    if isinstance(first, dict):
        config = first.get("generation_config")
        if isinstance(config, dict):
            max_out = config.get("max_output_tokens")
            if isinstance(max_out, int):
                return max_out
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


def _extract_total_tokens(response: Any) -> int | None:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        nested_response = getattr(response, "response", None)
        if nested_response is not None:
            usage = getattr(nested_response, "usage_metadata", None)
    if usage is None:
        return None
    total = getattr(usage, "total_token_count", None)
    if isinstance(total, int):
        return total
    prompt = getattr(usage, "prompt_token_count", None)
    candidates = getattr(usage, "candidates_token_count", None)
    if isinstance(prompt, int) and isinstance(candidates, int):
        return prompt + candidates
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


def _apply_google_clamp(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    protect_decision: dict[str, object],
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if str(protect_decision.get("decision") or "") != "clamp":
        return args, kwargs
    if protect_decision.get("apply_clamp_enabled") is not True:
        return args, kwargs
    clamp = protect_decision.get("clamp")
    if not isinstance(clamp, dict):
        return args, kwargs
    recommended = clamp.get("recommended_max_output_tokens")
    if not isinstance(recommended, int) or recommended < 1:
        return args, kwargs

    next_args = list(args)
    next_kwargs = dict(kwargs)

    if isinstance(next_kwargs.get("generation_config"), dict):
        generation_config = dict(next_kwargs["generation_config"])
        if isinstance(generation_config.get("max_output_tokens"), int):
            generation_config["max_output_tokens"] = min(int(generation_config["max_output_tokens"]), recommended)
        else:
            generation_config["max_output_tokens"] = recommended
        next_kwargs["generation_config"] = generation_config
        _mark_clamp_applied_if_changed(
            protect_decision,
            _extract_max_output_tokens(args, kwargs),
            _extract_max_output_tokens(tuple(next_args), next_kwargs),
        )
        return tuple(next_args), next_kwargs

    if next_args and isinstance(next_args[0], dict):
        payload = dict(next_args[0])
        payload_generation_config = payload.get("generation_config")
        generation_config = dict(payload_generation_config) if isinstance(payload_generation_config, dict) else {}
        if isinstance(generation_config.get("max_output_tokens"), int):
            generation_config["max_output_tokens"] = min(int(generation_config["max_output_tokens"]), recommended)
        else:
            generation_config["max_output_tokens"] = recommended
        payload["generation_config"] = generation_config
        next_args[0] = payload
        _mark_clamp_applied_if_changed(
            protect_decision,
            _extract_max_output_tokens(args, kwargs),
            _extract_max_output_tokens(tuple(next_args), next_kwargs),
        )
        return tuple(next_args), next_kwargs

    next_generation_config = next_kwargs.get("generation_config")
    generation_config = dict(next_generation_config) if isinstance(next_generation_config, dict) else {}
    generation_config["max_output_tokens"] = recommended
    next_kwargs["generation_config"] = generation_config
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
