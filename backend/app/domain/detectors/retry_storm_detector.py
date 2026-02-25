# Retry storm detector scaffold.
from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class RetryStormDetector(Detector):
    # Stub detector; no runtime behavior change yet.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        _ = ctx
        return []
