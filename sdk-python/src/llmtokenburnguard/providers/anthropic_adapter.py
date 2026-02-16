# Anthropic adapter scaffolding.
from llmtokenburnguard.logger import get_logger

logger = get_logger(__name__)


class AnthropicAdapter:
    # Adapter interface implementation for Anthropic responses.

    def extract_usage(self, response: object) -> dict[str, object]:
        # Extract normalized usage metadata from a provider response.
        try:
            _ = response
            # TODO: Parse Anthropic response usage schema.
            logger.debug("Anthropic adapter extract_usage called")
            return {}
        except Exception:
            logger.exception("Anthropic adapter extract_usage failed")
            raise
