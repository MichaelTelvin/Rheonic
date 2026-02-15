"""Gemini adapter scaffolding."""


class GeminiAdapter:
    """Adapter interface implementation for Gemini responses."""

    def extract_usage(self, response: object) -> dict[str, object]:
        """Extract normalized usage metadata from a provider response."""
        _ = response
        # TODO: Parse Gemini response schema.
        return {}
