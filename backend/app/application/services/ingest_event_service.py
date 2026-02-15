"""Application service for event ingestion."""


class IngestEventService:
    """Orchestrates ingest flow without transport or persistence details."""

    def ingest(self, payload: dict[str, object]) -> None:
        """Ingest a single event payload."""
        # TODO: Validate payload DTO and persist via repository abstractions.
        _ = payload
