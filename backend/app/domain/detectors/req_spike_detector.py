from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class ReqSpikeDetector(Detector):
    # Placeholder detector reserved for future request-spike heuristics.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        _ = ctx
        return []
