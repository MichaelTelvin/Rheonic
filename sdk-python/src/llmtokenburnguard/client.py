"""SDK client scaffolding."""


class LLMTokenBurnGuardClient:
    """Primary SDK client used by applications."""

    def __init__(self, api_key: str, base_url: str) -> None:
        """Initialize the SDK client."""
        self.api_key = api_key
        self.base_url = base_url
        # TODO: Add transport/session configuration.
