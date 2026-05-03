from django.conf import settings
from redis import Redis
from functools import lru_cache


@lru_cache
def get_redis_client() -> Redis:
    redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    return Redis.from_url(
        redis_url,
        decode_responses=True,
    )
