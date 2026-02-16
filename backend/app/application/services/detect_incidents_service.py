# Application service for incident detection.
from app.application.interfaces.cache_provider import RealtimeCounterStore
from app.application.interfaces.incident_repository import IncidentRepository
from app.domain.models.incident import Incident
from app.logger import get_logger

logger = get_logger(__name__)


class DetectIncidentsService:
    # Runs configured detectors over event streams.

    def __init__(
        self,
        incident_repository: IncidentRepository,
        realtime_counters: RealtimeCounterStore,
    ) -> None:
        # Initialize dependencies.
        self._incident_repository = incident_repository
        self._realtime_counters = realtime_counters

    def detect(self) -> list[object]:
        # Detect incidents and return incident DTOs.
        try:
            # TODO: Run domain detectors and persist incidents.
            logger.debug("Detect incidents service called")
            return []
        except Exception:
            logger.exception("Detect incidents service failed")
            raise

    def list_incidents(self, project_id: str, status: str = "open") -> list[Incident]:
        # List incidents for project and status.
        try:
            return self._incident_repository.list_by_project(project_id=project_id, status=status)
        except Exception:
            logger.exception("List incidents service failed", extra={"project_id": project_id, "status": status})
            raise

    def resolve_incident(self, incident_id: str) -> Incident | None:
        # Resolve incident and release dedupe lock.
        try:
            incident = self._incident_repository.resolve_incident(incident_id=incident_id)
            if incident is None:
                return None
            self._realtime_counters.release_incident_lock(
                project_id=incident.project_id,
                incident_type=incident.incident_type,
            )
            return incident
        except Exception:
            logger.exception("Resolve incident service failed", extra={"incident_id": incident_id})
            raise
