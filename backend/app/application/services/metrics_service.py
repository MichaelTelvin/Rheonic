"""Application service for metrics aggregation."""


class MetricsService:
    """Builds incident-first dashboard metrics."""

    def get_metrics(self) -> dict[str, object]:
        """Return computed metrics for API response serialization."""
        # TODO: Aggregate repository data into metrics DTOs.
        return {}
