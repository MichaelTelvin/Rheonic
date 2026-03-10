# Redis client scaffolding.

from redis import Redis

from app.config import Settings
from app.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    # Thin wrapper for Redis connectivity and commands.

    def __init__(self, redis_url: str | None = None) -> None:
        # Create a Redis client wrapper.
        try:
            resolved_redis_url = redis_url or Settings().redis_url
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

    def set_persistent(self, key: str, value: object) -> None:
        # Set value without expiration.
        try:
            self._redis.set(key, value)
        except Exception:
            logger.exception("Redis SET persistent failed", extra={"key": key})
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

    def zrem(self, key: str, *members: object) -> int:
        # Remove sorted set members.
        try:
            return int(self._redis.zrem(key, *members))
        except Exception:
            logger.exception("Redis ZREM failed", extra={"key": key})
            raise

    def lpush(self, key: str, value: object) -> int:
        # Push value to the head of a list and return the list length.
        try:
            return int(self._redis.lpush(key, value))
        except Exception:
            logger.exception("Redis LPUSH failed", extra={"key": key})
            raise

    def ltrim(self, key: str, start: int, stop: int) -> bool:
        # Trim list to the inclusive start/stop range.
        try:
            return bool(self._redis.ltrim(key, start, stop))
        except Exception:
            logger.exception("Redis LTRIM failed", extra={"key": key, "start": start, "stop": stop})
            raise

    def lrange(self, key: str, start: int, stop: int) -> list[object]:
        # Return list values for inclusive start/stop range.
        try:
            return list(self._redis.lrange(key, start, stop))
        except Exception:
            logger.exception("Redis LRANGE failed", extra={"key": key, "start": start, "stop": stop})
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

    def ping(self) -> bool:
        # Verify connectivity to Redis.
        try:
            return bool(self._redis.ping())
        except Exception:
            logger.exception("Redis PING failed")
            raise
