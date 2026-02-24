from llmtokenburnguard.protect_engine import LLMTBGValidationError

_SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "google")


def validate_provider_model(provider: str, model: str | None) -> None:
    normalized_provider = provider.strip().lower()
    if not normalized_provider:
        raise LLMTBGValidationError("LLMTBG: provider must be explicitly provided.")

    if normalized_provider not in _SUPPORTED_PROVIDERS:
        raise LLMTBGValidationError(f"LLMTBG: unsupported provider: {provider}")

    normalized_model = (model or "").strip()
    if not normalized_model:
        raise LLMTBGValidationError(f"LLMTBG: model must be explicitly provided for provider {normalized_provider}.")
