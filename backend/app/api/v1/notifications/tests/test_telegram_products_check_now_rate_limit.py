from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.products_handler import (
    MESSAGE_CHECK_RATE_LIMITED,
    TelegramProductsHandler,
)


class TelegramProductsCheckNowRateLimitTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.replies = Mock()
        self.user_context_resolver = Mock()
        self.action_rate_limiter = Mock()
        self.user = SimpleNamespace(pk=7)
        self.user_context = SimpleNamespace(
            user=self.user,
            telegram_chat_id="123",
        )
        self.user_context_resolver.resolve.return_value = (
            self.user_context
        )
        self.handler = TelegramProductsHandler(
            client=self.client,
            replies=self.replies,
            user_context_resolver=self.user_context_resolver,
            action_rate_limiter=self.action_rate_limiter,
            page_size=3,
        )
        self.target_id = uuid4()

    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "check_monitoring_target_now"
    )
    def test_check_now_limit_blocks_parser_operation(
        self,
        check_now_mock,
    ) -> None:
        self.action_rate_limiter.check_check_now.return_value = (
            SimpleNamespace(
                allowed=False,
                retry_after_seconds=23,
            )
        )

        self.handler.handle_callback(
            callback_query={
                "id": "callback-1",
                "from": {"id": 123},
                "data": f"target:check:{self.target_id}:1",
                "message": {
                    "message_id": 50,
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                },
            }
        )

        self.action_rate_limiter.check_check_now.assert_called_once_with(
            user_id=7,
        )
        self.client.answer_callback_query.assert_called_once_with(
            callback_query_id="callback-1",
            text=MESSAGE_CHECK_RATE_LIMITED.format(
                retry_after_seconds=23,
            ),
            show_alert=True,
        )
        check_now_mock.assert_not_called()
        self.client.send_message.assert_not_called()

    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "check_monitoring_target_now"
    )
    def test_allowed_check_reaches_service(
        self,
        check_now_mock,
    ) -> None:
        self.action_rate_limiter.check_check_now.return_value = (
            SimpleNamespace(
                allowed=True,
                retry_after_seconds=0,
            )
        )
        check_now_mock.side_effect = RuntimeError("stop after call")

        self.handler.handle_callback(
            callback_query={
                "id": "callback-1",
                "from": {"id": 123},
                "data": f"target:check:{self.target_id}:1",
                "message": {
                    "message_id": 50,
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                },
            }
        )

        check_now_mock.assert_called_once_with(
            user=self.user,
            target_id=self.target_id,
        )
