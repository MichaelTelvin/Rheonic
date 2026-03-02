# SDK rate limiter scaffolding.
from rheonic.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    # Client-side rate limiter helper for protect mode.

    def allow(self, key: str) -> bool:
        # Return whether request key should be allowed.
        try:
            _ = key
            # TODO: Implement local sliding-window limiter.
            logger.debug("SDK rate limiter allow called", extra={"key": key})
            return True
        except Exception:
            logger.exception("SDK rate limiter failed", extra={"key": key})
            raise
