from dataclasses import dataclass

from app.api.v1.common.redis import get_redis_client


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


def check_rate_limit(
        *,
        key: str,
        limit: int,
        window_seconds: int,
) -> RateLimitResult:
    redis_client = get_redis_client()

    current_count = redis_client.incr(key)

    if current_count == 1:
        redis_client.expire(key, window_seconds)

    ttl = redis_client.ttl(key)

    if ttl < 0:
        ttl = window_seconds

    remaining = max(limit - current_count, 0)

    if current_count > limit:
        return RateLimitResult(
            allowed=False,
            limit=limit,
            remaining=0,
            retry_after_seconds=ttl,
        )

    return RateLimitResult(
        allowed=True,
        limit=limit,
        remaining=remaining,
        retry_after_seconds=0,
    )
