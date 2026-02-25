from app.domain.detectors.contracts import DetectionContext, Signal
from app.domain.detectors.detector import Detector


class TokSpikeDetector(Detector):
    # Placeholder detector reserved for future token-spike heuristics.
    def detect(self, ctx: DetectionContext) -> list[Signal]:
        _ = ctx
        return []
