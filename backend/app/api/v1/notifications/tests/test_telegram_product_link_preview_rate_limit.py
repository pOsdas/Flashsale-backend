from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.product_link_handler import (
    TelegramProductLinkHandler,
)


class TelegramProductLinkPreviewRateLimitTests(SimpleTestCase):
    def setUp(self) -> None:
        self.replies = Mock()
        self.preview_service = Mock()
        self.pending_store = Mock()
        self.action_rate_limiter = Mock()
        self.handler = TelegramProductLinkHandler(
            replies=self.replies,
            preview_service=self.preview_service,
            pending_store=self.pending_store,
            action_rate_limiter=self.action_rate_limiter,
        )
        self.user_context = SimpleNamespace(
            user=SimpleNamespace(pk=7),
            telegram_chat_id="123",
        )

    @patch(
        "app.api.v1.notifications.telegram.product_link_handler."
        "find_existing_monitoring_target"
    )
    def test_preview_limit_blocks_preview_service(
        self,
        find_existing_mock,
    ) -> None:
        find_existing_mock.return_value = None
        self.action_rate_limiter.check_preview.return_value = (
            SimpleNamespace(
                allowed=False,
                retry_after_seconds=19,
            )
        )

        self.handler.handle(
            user_context=self.user_context,
            text=(
                "https://www.wildberries.ru/"
                "catalog/123/detail.aspx"
            ),
        )

        self.action_rate_limiter.check_preview.assert_called_once_with(
            user_id=7,
        )
        self.preview_service.preview_product.assert_not_called()
        self.replies.send_message.assert_called_once()
        self.assertIn(
            "19 секунд",
            self.replies.send_message.call_args.kwargs["text"],
        )
