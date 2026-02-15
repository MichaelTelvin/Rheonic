"""Application service for incident detection."""


class DetectIncidentsService:
    """Runs configured detectors over event streams."""

    def detect(self) -> list[object]:
        """Detect incidents and return incident DTOs."""
        # TODO: Run domain detectors and persist incidents.
        return []
