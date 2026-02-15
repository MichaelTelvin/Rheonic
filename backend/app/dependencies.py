"""Dependency wiring for API routes."""

from app.application.services.detect_incidents_service import DetectIncidentsService
from app.application.services.ingest_event_service import IngestEventService


def get_ingest_event_service() -> IngestEventService:
    """Provide an ingest event service instance."""
    # TODO: Inject repository and provider implementations.
    return IngestEventService()


def get_detect_incidents_service() -> DetectIncidentsService:
    """Provide an incident detection service instance."""
    # TODO: Inject detector and repository dependencies.
    return DetectIncidentsService()
