# Gemini adapter scaffolding.
from llmtokenburnguard.logger import get_logger

logger = get_logger(__name__)


class GeminiAdapter:
    # Adapter interface implementation for Gemini responses.

    def extract_usage(self, response: object) -> dict[str, object]:
        # Extract normalized usage metadata from a provider response.
        try:
            _ = response
            # TODO: Parse Gemini response usage schema.
            logger.debug("Gemini adapter extract_usage called")
            return {}
        except Exception:
            logger.exception("Gemini adapter extract_usage failed")
            raise
