"""Application service for reconciliation jobs."""


class ReconciliationService:
    """Coordinates periodic reconciliation of usage and cost records."""

    def reconcile(self) -> None:
        """Run a reconciliation pass."""
        # TODO: Compare provider usage against internal aggregates.
