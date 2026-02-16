# SDK client scaffolding.
from llmtokenburnguard.logger import configure_logging, get_logger

logger = get_logger(__name__)


class LLMTokenBurnGuardClient:
    # Primary SDK client used by applications.

    def __init__(self, api_key: str, base_url: str) -> None:
        # Initialize the SDK client.
        try:
            configure_logging()
            self.api_key = api_key
            self.base_url = base_url
            # TODO: Add transport/session configuration.
            logger.info("SDK client initialized")
        except Exception:
            logger.exception("SDK client initialization failed")
            raise
