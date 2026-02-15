"""SDK rate limiter scaffolding."""


class RateLimiter:
    """Client-side rate limiter helper for protect mode."""

    def allow(self, key: str) -> bool:
        """Return whether request key should be allowed."""
        _ = key
        # TODO: Implement local sliding-window limiter.
        return True
