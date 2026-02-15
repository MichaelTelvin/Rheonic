"""Event builder scaffolding."""


class EventBuilder:
    """Builds normalized usage events from provider responses."""

    def build(self, payload: dict[str, object]) -> dict[str, object]:
        """Build a backend-compatible event payload."""
        _ = payload
        # TODO: Normalize provider payload into SDK event schema.
        return {}
