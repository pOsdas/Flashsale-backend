from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.pending_product import (
    PendingTelegramProduct,
)
from app.api.v1.notifications.telegram.product_callback_handler import (
    TelegramProductCallbackHandler,
)


class TelegramProductCallbackHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.pending_store = Mock()
        self.user_context_resolver = Mock()
        self.handler = TelegramProductCallbackHandler(
            client=self.client,
            pending_store=self.pending_store,
            user_context_resolver=self.user_context_resolver,
        )
        self.pending_product = PendingTelegramProduct(
            token="token",
            user_id="7",
            telegram_chat_id="123",
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
        self.user = SimpleNamespace(pk=7)
        self.user_context_resolver.resolve.return_value = (
            SimpleNamespace(
                user=self.user,
                telegram_chat_id="123",
            )
        )
        self.pending_store.get.return_value = self.pending_product
        self.pending_store.acquire_lock.return_value = True

    @patch(
        "app.api.v1.notifications.telegram.product_callback_handler."
        "create_monitoring_target"
    )
    @patch(
        "app.api.v1.notifications.telegram.product_callback_handler."
        "find_existing_monitoring_target"
    )
    def test_add_callback_creates_target(
        self,
        find_existing_mock,
        create_target_mock,
    ) -> None:
        find_existing_mock.return_value = None
        create_target_mock.return_value = SimpleNamespace(
            title="Товар",
            external_id="123",
            url=self.pending_product.url,
            marketplace="wb",
            check_interval_minutes=60,
        )

        self.handler.handle(
            callback_query=self._callback("product:add:token")
        )

        create_target_mock.assert_called_once()
        self.pending_store.delete.assert_called_once_with(
            token="token"
        )
        self.client.edit_message_text.assert_called_once()

    @patch(
        "app.api.v1.notifications.telegram.product_callback_handler."
        "create_monitoring_target"
    )
    @patch(
        "app.api.v1.notifications.telegram.product_callback_handler."
        "find_existing_monitoring_target"
    )
    def test_duplicate_callback_does_not_create_target(
        self,
        find_existing_mock,
        create_target_mock,
    ) -> None:
        find_existing_mock.return_value = SimpleNamespace(
            id="target-id",
            title="Товар",
            external_id="123",
            url=self.pending_product.url,
            marketplace="wb",
            check_interval_minutes=60,
        )

        self.handler.handle(
            callback_query=self._callback("product:add:token")
        )

        create_target_mock.assert_not_called()
        self.pending_store.delete.assert_called_once_with(
            token="token"
        )
        edit_call = self.client.edit_message_text.call_args.kwargs
        self.assertIn("уже отслеживается", edit_call["text"])

    def test_cancel_callback_removes_pending_product(self) -> None:
        self.handler.handle(
            callback_query=self._callback("product:cancel:token")
        )

        self.pending_store.delete.assert_called_once_with(
            token="token"
        )
        self.client.edit_message_text.assert_called_once()

    @staticmethod
    def _callback(data: str) -> dict:
        return {
            "id": "callback-1",
            "from": {"id": 123},
            "data": data,
            "message": {
                "message_id": 50,
                "chat": {
                    "id": 123,
                    "type": "private",
                },
            },
        }
