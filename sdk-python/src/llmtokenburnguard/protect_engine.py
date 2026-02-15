"""Protect engine scaffolding."""


class ProtectEngine:
    """Applies deterministic local protect-mode decisions."""

    def evaluate(self, context: dict[str, object]) -> dict[str, object]:
        """Return protect decision metadata for a request."""
        _ = context
        # TODO: Apply local policy actions in deterministic order.
        return {}
