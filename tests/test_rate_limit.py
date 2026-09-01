import uuid
from unittest.mock import patch

from redis.exceptions import RedisError

from app.services.rate_limit import clear_attempts, record_attempt, retry_after


class UnavailableRedis:
    def get(self, key: str) -> None:
        raise RedisError("unavailable")

    def incr(self, key: str) -> None:
        raise RedisError("unavailable")

    def delete(self, key: str) -> None:
        raise RedisError("unavailable")


def test_local_fallback_enforces_limit_when_redis_is_unavailable() -> None:
    identity = f"fallback-{uuid.uuid4().hex}"
    with patch("app.services.rate_limit.get_rate_limit_redis", return_value=UnavailableRedis()):
        assert retry_after("test", identity, 2) is None
        record_attempt("test", identity, 60)
        record_attempt("test", identity, 60)

        wait = retry_after("test", identity, 2)
        assert wait is not None
        assert 1 <= wait <= 60

        clear_attempts("test", identity)
        assert retry_after("test", identity, 2) is None
