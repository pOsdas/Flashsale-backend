from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.monitoring.services.product_preview import (
    ProductPreviewData,
)
from app.api.v1.notifications.telegram.pending_product import (
    PendingTelegramProduct,
)
from app.api.v1.notifications.telegram.product_link_handler import (
    TelegramProductLinkHandler,
)


class TelegramProductLinkHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.replies = Mock()
        self.preview_service = Mock()
        self.pending_store = Mock()
        self.handler = TelegramProductLinkHandler(
            replies=self.replies,
            preview_service=self.preview_service,
            pending_store=self.pending_store,
        )
        self.user_context = SimpleNamespace(
            user=SimpleNamespace(pk=7),
            telegram_chat_id="123",
        )

    @patch(
        "app.api.v1.notifications.telegram.product_link_handler."
        "check_rate_limit"
    )
    def test_sends_preview_with_inline_keyboard(
        self,
        check_rate_limit_mock,
    ) -> None:
        check_rate_limit_mock.return_value = SimpleNamespace(
            allowed=True,
        )
        self.preview_service.preview_product.return_value = (
            ProductPreviewData(
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
                raw_data={},
            )
        )
        self.pending_store.create.return_value = (
            PendingTelegramProduct(
                token="token",
                user_id="7",
                telegram_chat_id="123",
                marketplace="wb",
                url=(
                    "https://www.wildberries.ru/"
                    "catalog/123/detail.aspx"
                ),
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
        )
        self.replies.send_message.return_value = True

        self.handler.handle(
            user_context=self.user_context,
            text=(
                "https://www.wildberries.ru/"
                "catalog/123/detail.aspx"
            ),
        )

        self.preview_service.preview_product.assert_called_once_with(
            marketplace="wb",
            url=(
                "https://www.wildberries.ru/"
                "catalog/123/detail.aspx"
            ),
        )
        send_call = self.replies.send_message.call_args.kwargs
        self.assertEqual(send_call["chat_id"], "123")
        self.assertIn("Найден товар", send_call["text"])
        self.assertEqual(
            send_call["reply_markup"]["inline_keyboard"][0][0][
                "callback_data"
            ],
            "product:add:token",
        )

    def test_rejects_message_without_supported_url(self) -> None:
        self.handler.handle(
            user_context=self.user_context,
            text="обычный текст",
        )

        self.preview_service.preview_product.assert_not_called()
        self.replies.send_message.assert_called_once()
