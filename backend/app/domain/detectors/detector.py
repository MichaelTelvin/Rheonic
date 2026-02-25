from abc import ABC, abstractmethod

from app.domain.detectors.contracts import DetectionContext, Signal


class Detector(ABC):
    # Interface for deterministic signal detectors.

    @abstractmethod
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        raise NotImplementedError
