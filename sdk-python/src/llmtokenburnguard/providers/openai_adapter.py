"""OpenAI adapter scaffolding."""


class OpenAIAdapter:
    """Adapter interface implementation for OpenAI responses."""

    def extract_usage(self, response: object) -> dict[str, object]:
        """Extract normalized usage metadata from a provider response."""
        _ = response
        # TODO: Parse OpenAI response schema.
        return {}
