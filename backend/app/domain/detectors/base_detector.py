# Detector interface for anomaly detection.
from abc import ABC, abstractmethod

from app.domain.models.event import Event
from app.domain.models.incident import Incident


class BaseDetector(ABC):
    # Base interface for deterministic and explainable detectors.

    @abstractmethod
    def detect(self, events: list[Event]) -> list[Incident]:
        # Detect incidents from a list of events.
        raise NotImplementedError
