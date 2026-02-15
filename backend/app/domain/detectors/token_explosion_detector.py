"""Token explosion detector."""

from app.domain.detectors.base_detector import BaseDetector
from app.domain.models.event import Event
from app.domain.models.incident import Incident


class TokenExplosionDetector(BaseDetector):
    """Detects unusually large token usage jumps."""

    def detect(self, events: list[Event]) -> list[Incident]:
        _ = events
        # TODO: Implement token explosion detection logic.
        return []
