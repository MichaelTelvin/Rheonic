"""Burn rate spike detector."""

from app.domain.detectors.base_detector import BaseDetector
from app.domain.models.event import Event
from app.domain.models.incident import Incident


class BurnSpikeDetector(BaseDetector):
    """Detects sudden cost burn-rate spikes."""

    def detect(self, events: list[Event]) -> list[Incident]:
        _ = events
        # TODO: Implement burn-rate spike thresholds from config.
        return []
