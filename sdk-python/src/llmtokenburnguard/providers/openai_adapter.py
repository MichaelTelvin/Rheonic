# OpenAI instrumentation wrapper.
import inspect
from time import perf_counter
from typing import Any

from llmtokenburnguard.client import Client, get_default_client
from llmtokenburnguard.event_builder import build_event
from llmtokenburnguard.logger import get_logger

logger = get_logger(__name__)


def instrument_openai(
    openai_client: Any,
    client: Client | None = None,
    environment: str | None = None,
    endpoint: str | None = None,
    feature: str | None = None,
) -> Any:
    # Instrument chat.completions.create and emit usage events.
    resolved_client = client or get_default_client()
    if resolved_client is None:
        return openai_client

    chat = getattr(openai_client, "chat", None)
    completions = getattr(chat, "completions", None)
    original_create = getattr(completions, "create", None)
    if completions is None or not callable(original_create):
        return openai_client

    if inspect.iscoroutinefunction(original_create):

        async def wrapped_create(*args: Any, **kwargs: Any) -> Any:
            # Async wrapper for AsyncOpenAI style clients.
            started_at = perf_counter()
            requested_model = _extract_requested_model(args, kwargs)
            try:
                response = await original_create(*args, **kwargs)
                _capture_success(
                    sdk_client=resolved_client,
                    response=response,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    requested_model=requested_model,
                    environment=environment,
                    endpoint=endpoint,
                    feature=feature,
                )
                return response
            except Exception as exc:
                _capture_failure(
                    sdk_client=resolved_client,
                    exc=exc,
                    latency_ms=int((perf_counter() - started_at) * 1000),
                    requested_model=requested_model,
                    environment=environment,
                    endpoint=endpoint,
                    feature=feature,
                )
                raise

        completions.create = wrapped_create
        return openai_client

    def wrapped_create(*args: Any, **kwargs: Any) -> Any:
        # Sync wrapper for OpenAI client.
        started_at = perf_counter()
        requested_model = _extract_requested_model(args, kwargs)
        try:
            response = original_create(*args, **kwargs)
            _capture_success(
                sdk_client=resolved_client,
                response=response,
                latency_ms=int((perf_counter() - started_at) * 1000),
                requested_model=requested_model,
                environment=environment,
                endpoint=endpoint,
                feature=feature,
            )
            return response
        except Exception as exc:
            _capture_failure(
                sdk_client=resolved_client,
                exc=exc,
                latency_ms=int((perf_counter() - started_at) * 1000),
                requested_model=requested_model,
                environment=environment,
                endpoint=endpoint,
                feature=feature,
            )
            raise

    completions.create = wrapped_create
    return openai_client


def _capture_success(
    sdk_client: Client,
    response: Any,
    latency_ms: int,
    requested_model: str | None,
    environment: str | None,
    endpoint: str | None,
    feature: str | None,
) -> None:
    # Emit success event with usage and latency.
    try:
        response_model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None)
        sdk_client.capture_event(
            build_event(
                provider="openai",
                model=response_model if isinstance(response_model, str) else requested_model,
                environment=environment or sdk_client.environment,
                request={"endpoint": endpoint, "feature": feature},
                response={
                    "latency_ms": latency_ms,
                    "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
                    "http_status": 200,
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture OpenAI success event")


def _capture_failure(
    sdk_client: Client,
    exc: Exception,
    latency_ms: int,
    requested_model: str | None,
    environment: str | None,
    endpoint: str | None,
    feature: str | None,
) -> None:
    # Emit error event when provider call fails.
    try:
        http_status = _extract_http_status(exc)
        sdk_client.capture_event(
            build_event(
                provider="openai",
                model=requested_model,
                environment=environment or sdk_client.environment,
                request={"endpoint": endpoint, "feature": feature},
                response={
                    "latency_ms": latency_ms,
                    "error_type": exc.__class__.__name__ or "unknown",
                    "http_status": http_status,
                },
            )
        )
    except Exception:
        logger.exception("Failed to capture OpenAI failure event")


def _extract_requested_model(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    # Extract model argument from create call input.
    model = kwargs.get("model")
    if isinstance(model, str):
        return model

    first = args[0] if args else None
    if isinstance(first, dict):
        arg_model = first.get("model")
        if isinstance(arg_model, str):
            return arg_model

    return None


def _extract_http_status(exc: Exception) -> int | None:
    # Read status code from common OpenAI exception attributes.
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
