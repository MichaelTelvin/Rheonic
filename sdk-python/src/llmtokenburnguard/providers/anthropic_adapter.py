"""Anthropic adapter scaffolding."""


class AnthropicAdapter:
    """Adapter interface implementation for Anthropic responses."""

    def extract_usage(self, response: object) -> dict[str, object]:
        """Extract normalized usage metadata from a provider response."""
        _ = response
        # TODO: Parse Anthropic response schema.
        return {}
