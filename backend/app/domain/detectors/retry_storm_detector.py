"""Retry storm detector."""

from app.domain.detectors.base_detector import BaseDetector
from app.domain.models.event import Event
from app.domain.models.incident import Incident


class RetryStormDetector(BaseDetector):
    """Detects abnormally frequent retry patterns."""

    def detect(self, events: list[Event]) -> list[Incident]:
        _ = events
        # TODO: Implement deterministic retry storm heuristics.
        return []
