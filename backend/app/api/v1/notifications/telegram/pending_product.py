import secrets
from dataclasses import asdict, dataclass
from typing import Any

from django.core.cache import cache


PENDING_PRODUCT_KEY_PREFIX = "telegram:pending-product:"
PENDING_PRODUCT_LOCK_KEY_PREFIX = "telegram:pending-product-lock:"


class PendingProductStoreError(RuntimeError):
    """Pending Telegram product state could not be stored."""


@dataclass(frozen=True, slots=True)
class PendingTelegramProduct:
    token: str
    user_id: str
    telegram_chat_id: str
    marketplace: str
    url: str
    external_id: str
    title: str
    seller_name: str
    brand: str
    price: int | None
    old_price: int | None
    currency: str
    is_available: bool
    rating: float | None
    reviews_count: int | None


class TelegramPendingProductStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 600,
        lock_seconds: int = 30,
        cache_backend: Any = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Pending product TTL must be positive")

        if lock_seconds <= 0:
            raise ValueError("Pending product lock TTL must be positive")

        self.ttl_seconds = ttl_seconds
        self.lock_seconds = lock_seconds
        self.cache = cache_backend or cache

    def create(
        self,
        *,
        user_id: int | str,
        telegram_chat_id: int | str,
        marketplace: str,
        url: str,
        external_id: str,
        title: str,
        seller_name: str,
        brand: str,
        price: int | None,
        old_price: int | None,
        currency: str,
        is_available: bool,
        rating: float | None,
        reviews_count: int | None,
    ) -> PendingTelegramProduct:
        for _ in range(5):
            token = secrets.token_urlsafe(12)
            pending_product = PendingTelegramProduct(
                token=token,
                user_id=str(user_id),
                telegram_chat_id=str(telegram_chat_id),
                marketplace=marketplace,
                url=url,
                external_id=external_id,
                title=title,
                seller_name=seller_name,
                brand=brand,
                price=price,
                old_price=old_price,
                currency=currency,
                is_available=is_available,
                rating=rating,
                reviews_count=reviews_count,
            )

            created = self.cache.add(
                self._build_key(token=token),
                asdict(pending_product),
                timeout=self.ttl_seconds,
            )

            if created:
                return pending_product

        raise PendingProductStoreError(
            "Не удалось сохранить подтверждение товара."
        )

    def get(
        self,
        *,
        token: str,
    ) -> PendingTelegramProduct | None:
        normalized_token = str(token).strip()

        if not normalized_token:
            return None

        value = self.cache.get(
            self._build_key(token=normalized_token)
        )

        if not isinstance(value, dict):
            return None

        try:
            return PendingTelegramProduct(**value)
        except TypeError:
            return None

    def delete(self, *, token: str) -> None:
        self.cache.delete(
            self._build_key(token=token)
        )

    def acquire_lock(self, *, token: str) -> bool:
        return bool(
            self.cache.add(
                self._build_lock_key(token=token),
                "1",
                timeout=self.lock_seconds,
            )
        )

    def release_lock(self, *, token: str) -> None:
        self.cache.delete(
            self._build_lock_key(token=token)
        )

    @staticmethod
    def _build_key(*, token: str) -> str:
        return f"{PENDING_PRODUCT_KEY_PREFIX}{token}"

    @staticmethod
    def _build_lock_key(*, token: str) -> str:
        return f"{PENDING_PRODUCT_LOCK_KEY_PREFIX}{token}"
