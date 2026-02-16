# Loop suspect detector.
from app.domain.detectors.base_detector import BaseDetector
from app.domain.models.event import Event
from app.domain.models.incident import Incident


class LoopDetector(BaseDetector):
    # Detects likely response/request loop patterns.
    def detect(self, events: list[Event]) -> list[Incident]:
        _ = events
        # TODO: Implement deterministic loop detection.
        return []
