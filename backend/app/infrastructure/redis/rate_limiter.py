"""Rate limiter scaffolding."""


class RateLimiter:
    """Infrastructure helper for sliding-window rate limits."""

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return whether request is allowed for key within the window."""
        _ = (key, limit, window_seconds)
        # TODO: Implement deterministic sliding-window enforcement.
        return True
