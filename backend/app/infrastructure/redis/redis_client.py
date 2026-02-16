# Redis client scaffolding.
import os

from redis import Redis

from app.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    # Thin wrapper for Redis connectivity and commands.

    def __init__(self, redis_url: str | None = None) -> None:
        # Create a Redis client wrapper.
        try:
            self._redis = Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            logger.info("Redis client initialized")
        except Exception:
            logger.exception("Failed to initialize Redis client")
            raise

    def get(self, key: str) -> object | None:
        # Get value by key from Redis.
        try:
            return self._redis.get(key)
        except Exception:
            logger.exception("Redis GET failed", extra={"key": key})
            raise

    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        # Set value with TTL in Redis.
        try:
            self._redis.set(key, value, ex=ttl_seconds)
        except Exception:
            logger.exception("Redis SET failed", extra={"key": key, "ttl_seconds": ttl_seconds})
            raise

    def incr(self, key: str) -> int:
        # Increment a key by one and return its value.
        try:
            return int(self._redis.incr(key))
        except Exception:
            logger.exception("Redis INCR failed", extra={"key": key})
            raise

    def incrby(self, key: str, amount: int) -> int:
        # Increment a key by amount and return its value.
        try:
            return int(self._redis.incrby(key, amount))
        except Exception:
            logger.exception("Redis INCRBY failed", extra={"key": key, "amount": amount})
            raise

    def expire(self, key: str, ttl_seconds: int) -> bool:
        # Set TTL on key and return operation success.
        try:
            return bool(self._redis.expire(key, ttl_seconds))
        except Exception:
            logger.exception("Redis EXPIRE failed", extra={"key": key, "ttl_seconds": ttl_seconds})
            raise
