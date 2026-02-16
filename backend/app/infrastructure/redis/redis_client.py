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
            resolved_redis_url = redis_url or os.getenv("REDIS_URL")
            if not resolved_redis_url:
                raise ValueError("REDIS_URL is not set")
            self._redis = Redis.from_url(resolved_redis_url)
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

    def set_nx_ex(self, key: str, value: object, ttl_seconds: int) -> bool:
        # Set key only when absent and apply TTL.
        try:
            return bool(self._redis.set(key, value, nx=True, ex=ttl_seconds))
        except Exception:
            logger.exception("Redis SET NX EX failed", extra={"key": key, "ttl_seconds": ttl_seconds})
            raise

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        # Add scored members to sorted set.
        try:
            return int(self._redis.zadd(key, mapping))
        except Exception:
            logger.exception("Redis ZADD failed", extra={"key": key})
            raise

    def zremrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> int:
        # Remove sorted set members by score range.
        try:
            return int(self._redis.zremrangebyscore(key, min_score, max_score))
        except Exception:
            logger.exception("Redis ZREMRANGEBYSCORE failed", extra={"key": key})
            raise

    def zcard(self, key: str) -> int:
        # Return sorted set cardinality.
        try:
            return int(self._redis.zcard(key))
        except Exception:
            logger.exception("Redis ZCARD failed", extra={"key": key})
            raise

    def zrangebyscore(self, key: str, min_score: int | float, max_score: int | float) -> list[object]:
        # Return sorted set members by score range.
        try:
            return list(self._redis.zrangebyscore(key, min_score, max_score))
        except Exception:
            logger.exception("Redis ZRANGEBYSCORE failed", extra={"key": key})
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

    def delete(self, key: str) -> int:
        # Delete key and return deletion count.
        try:
            return int(self._redis.delete(key))
        except Exception:
            logger.exception("Redis DELETE failed", extra={"key": key})
            raise
