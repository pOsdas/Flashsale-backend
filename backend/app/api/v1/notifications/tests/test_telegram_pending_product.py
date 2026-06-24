from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.pending_product import (
    TelegramPendingProductStore,
)


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add(self, key, value, timeout=None):
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


class TelegramPendingProductStoreTests(SimpleTestCase):
    def setUp(self) -> None:
        self.cache = FakeCache()
        self.store = TelegramPendingProductStore(
            ttl_seconds=600,
            lock_seconds=30,
            cache_backend=self.cache,
        )

    def test_create_and_get_pending_product(self) -> None:
        created = self.store.create(
            user_id=10,
            telegram_chat_id=20,
            marketplace="wb",
            url="https://www.wildberries.ru/catalog/123/detail.aspx",
            external_id="123",
            title="Товар",
            seller_name="Продавец",
            brand="Бренд",
            price=1000,
            old_price=1200,
            currency="RUB",
            is_available=True,
            rating=4.8,
            reviews_count=15,
        )

        loaded = self.store.get(token=created.token)

        self.assertEqual(loaded, created)

    def test_lock_is_exclusive_until_release(self) -> None:
        self.assertTrue(
            self.store.acquire_lock(token="token")
        )
        self.assertFalse(
            self.store.acquire_lock(token="token")
        )

        self.store.release_lock(token="token")

        self.assertTrue(
            self.store.acquire_lock(token="token")
        )
