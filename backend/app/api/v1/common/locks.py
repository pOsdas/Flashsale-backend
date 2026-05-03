import uuid
from redis import Redis

from app.api.v1.common import get_redis_client


class RedisLock:
    def __init__(
            self,
            *,
            key: str,
            ttl: int = 10,
    ) -> None:
        self.redis: Redis = get_redis_client()
        self.key = key
        self.ttl = ttl
        self.value = str(uuid.uuid4())

    def acquire(self) -> bool:
        return self.redis.set(
            self.key,
            self.value,
            nx=True,
            ex=self.ttl,
        )

    def release(self) -> None:
        current_value = self.redis.get(self.key)

        if current_value == self.value:
            self.redis.delete(self.key)

    def __enter__(self) -> "RedisLock":
        acquired = self.acquire()
        if not acquired:
            raise RuntimeError(f"Lock {self.key} is already acquired")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
