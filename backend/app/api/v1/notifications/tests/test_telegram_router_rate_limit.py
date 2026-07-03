from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.router import (
    MESSAGE_CALLBACK_RATE_LIMITED,
    TelegramUpdateRouter,
)


class TelegramRouterRateLimitTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.replies = Mock()
        self.start_handler = Mock()
        self.help_handler = Mock()
        self.user_context_resolver = Mock()
        self.product_link_handler = Mock()
        self.product_callback_handler = Mock()
        self.products_handler = Mock()
        self.notifications_handler = Mock()
        self.target_alert_settings_handler = Mock()
        self.target_interval_handler = Mock()
        self.target_history_handler = Mock()
        self.action_rate_limiter = Mock()

        self.router = TelegramUpdateRouter(
            client=self.client,
            replies=self.replies,
            start_handler=self.start_handler,
            help_handler=self.help_handler,
            user_context_resolver=self.user_context_resolver,
            product_link_handler=self.product_link_handler,
            product_callback_handler=self.product_callback_handler,
            products_handler=self.products_handler,
            notifications_handler=self.notifications_handler,
            target_alert_settings_handler=(
                self.target_alert_settings_handler
            ),
            target_interval_handler=self.target_interval_handler,
            target_history_handler=self.target_history_handler,
            action_rate_limiter=self.action_rate_limiter,
        )

    def test_callback_limit_blocks_dispatch(self) -> None:
        self.action_rate_limiter.check_callback.return_value = (
            SimpleNamespace(
                allowed=False,
                retry_after_seconds=12,
            )
        )
        callback_query = {
            "id": "callback-1",
            "from": {"id": 123},
            "message": {
                "message_id": 10,
                "chat": {
                    "id": 123,
                    "type": "private",
                },
            },
            "data": "products:page:2",
        }

        self.router.handle_update(
            update={
                "update_id": 1,
                "callback_query": callback_query,
            }
        )

        self.action_rate_limiter.check_callback.assert_called_once_with(
            telegram_user_id="123",
        )
        self.client.answer_callback_query.assert_called_once_with(
            callback_query_id="callback-1",
            text=MESSAGE_CALLBACK_RATE_LIMITED.format(
                retry_after_seconds=12,
            ),
            show_alert=True,
        )
        self.product_callback_handler.can_handle.assert_not_called()
        self.notifications_handler.can_handle.assert_not_called()
        self.products_handler.handle_callback.assert_not_called()

    def test_allowed_callback_continues_to_handler(self) -> None:
        self.action_rate_limiter.check_callback.return_value = (
            SimpleNamespace(
                allowed=True,
                retry_after_seconds=0,
            )
        )
        self.product_callback_handler.can_handle.return_value = True
        callback_query = {
            "id": "callback-1",
            "from": {"id": 123},
            "message": {
                "message_id": 10,
                "chat": {
                    "id": 123,
                    "type": "private",
                },
            },
            "data": "product:add:token",
        }

        self.router.handle_update(
            update={
                "update_id": 1,
                "callback_query": callback_query,
            }
        )

        self.product_callback_handler.handle.assert_called_once_with(
            callback_query=callback_query,
        )
