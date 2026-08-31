import hashlib
import logging
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


def _key(scope: str, identity: str) -> str:
    digest = hashlib.sha256(identity.casefold().encode()).hexdigest()
    return f"neria:rate:{scope}:{digest}"


@lru_cache
def get_rate_limit_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def retry_after(scope: str, identity: str, limit: int) -> int | None:
    try:
        client = get_rate_limit_redis()
        key = _key(scope, identity)
        value = client.get(key)
        if value is None or int(value) < limit:
            return None
        ttl = client.ttl(key)
        return max(ttl, 1)
    except (RedisError, ValueError):
        logger.exception("Rate limiter unavailable; allowing request")
        return None


def record_attempt(scope: str, identity: str, window_seconds: int) -> None:
    try:
        client = get_rate_limit_redis()
        key = _key(scope, identity)
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
    except RedisError:
        logger.exception("Rate limiter unavailable; attempt was not recorded")


def clear_attempts(scope: str, identity: str) -> None:
    try:
        get_rate_limit_redis().delete(_key(scope, identity))
    except RedisError:
        logger.exception("Rate limiter unavailable; attempts were not cleared")
