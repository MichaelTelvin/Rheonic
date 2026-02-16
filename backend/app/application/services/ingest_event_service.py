# Application service for event ingestion.
from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.event_repository import EventRepository
from app.domain.models.event import Event
from app.logger import get_logger

logger = get_logger(__name__)


class IngestEventService:
    # Orchestrates ingest flow without transport or persistence details.

    def __init__(
        self,
        event_repository: EventRepository,
        realtime_counters: RealtimeCounterStore,
    ) -> None:
        # Initialize service dependencies.
        self._event_repository = event_repository
        self._realtime_counters = realtime_counters

    def ingest(self, event: Event) -> None:
        # Persist a single event and update realtime counters.
        try:
            # persist event to durable store
            self._event_repository.add(event)

            # update realtime 60s counters
            self._realtime_counters.increment_project_60s(
                project_id=event.project_id,
                total_tokens=event.total_tokens,
            )
            logger.info("Event ingested", extra={"project_id": event.project_id, "event_id": event.id})
        except Exception:
            logger.exception("Ingest service failed", extra={"project_id": event.project_id})
            raise
