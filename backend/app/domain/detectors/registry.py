from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class DetectorRegistry:
    # Runs configured detectors and aggregates emitted signals.

    def __init__(self, detectors: list[Detector]) -> None:
        self._detectors = detectors

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        signals: list[Signal] = []
        for detector in self._detectors:
            signals.extend(detector.detect(ctx))
        return signals
