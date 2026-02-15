"""Gemini cost provider scaffold."""

from app.application.interfaces.cost_provider import CostProvider


class GeminiCostProvider(CostProvider):
    """Calculates cost estimates for Gemini usage."""

    def calculate_cost(self, usage: dict[str, object]) -> float:
        _ = usage
        # TODO: Map usage metadata to Gemini pricing.
        return 0.0
