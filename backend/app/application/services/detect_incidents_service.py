# Application service for incident detection.
from app.logger import get_logger

logger = get_logger(__name__)


class DetectIncidentsService:
    # Runs configured detectors over event streams.

    def detect(self) -> list[object]:
        # Detect incidents and return incident DTOs.
        try:
            # TODO: Run domain detectors and persist incidents.
            logger.debug("Detect incidents service called")
            return []
        except Exception:
            logger.exception("Detect incidents service failed")
            raise
