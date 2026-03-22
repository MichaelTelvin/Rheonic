from rheonic.config import sdk_config
from rheonic.protect_engine import RHEONICValidationError


def validate_provider_model(provider: str, model: str | None) -> None:
    normalized_provider = provider.strip().lower()
    if not normalized_provider:
        raise RHEONICValidationError("RHEONIC: provider must be explicitly provided.")

    if normalized_provider not in sdk_config.supported_providers:
        raise RHEONICValidationError(f"RHEONIC: unsupported provider: {provider}")

    normalized_model = (model or "").strip()
    if not normalized_model:
        raise RHEONICValidationError(f"RHEONIC: model must be explicitly provided for provider {normalized_provider}.")
