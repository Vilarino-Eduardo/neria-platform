import hashlib
import logging
import time
from functools import lru_cache
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import get_settings

logger = logging.getLogger(__name__)
_fallback_attempts: dict[str, tuple[int, float]] = {}
_fallback_lock = Lock()


def _key(scope: str, identity: str) -> str:
    digest = hashlib.sha256(identity.casefold().encode()).hexdigest()
    return f"neria:rate:{scope}:{digest}"


@lru_cache
def get_rate_limit_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _fallback_retry_after(key: str, limit: int) -> int | None:
    now = time.monotonic()
    with _fallback_lock:
        entry = _fallback_attempts.get(key)
        if entry is None:
            return None
        count, expires_at = entry
        if expires_at <= now:
            _fallback_attempts.pop(key, None)
            return None
        return max(1, int(expires_at - now)) if count >= limit else None


def _fallback_record(key: str, window_seconds: int) -> None:
    now = time.monotonic()
    with _fallback_lock:
        count, expires_at = _fallback_attempts.get(key, (0, now + window_seconds))
        if expires_at <= now:
            count, expires_at = 0, now + window_seconds
        _fallback_attempts[key] = (count + 1, expires_at)


def _fallback_clear(key: str) -> None:
    with _fallback_lock:
        _fallback_attempts.pop(key, None)


def retry_after(scope: str, identity: str, limit: int) -> int | None:
    key = _key(scope, identity)
    try:
        client = get_rate_limit_redis()
        value = client.get(key)
        if value is None or int(value) < limit:
            return None
        ttl = client.ttl(key)
        return max(ttl, 1)
    except (RedisError, ValueError):
        logger.exception("Rate limiter unavailable; using local fallback")
        return _fallback_retry_after(key, limit)


def record_attempt(scope: str, identity: str, window_seconds: int) -> None:
    key = _key(scope, identity)
    try:
        client = get_rate_limit_redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
    except RedisError:
        logger.exception("Rate limiter unavailable; recording in local fallback")
        _fallback_record(key, window_seconds)


def clear_attempts(scope: str, identity: str) -> None:
    key = _key(scope, identity)
    _fallback_clear(key)
    try:
        get_rate_limit_redis().delete(key)
    except RedisError:
        logger.exception("Rate limiter unavailable; attempts were not cleared")
