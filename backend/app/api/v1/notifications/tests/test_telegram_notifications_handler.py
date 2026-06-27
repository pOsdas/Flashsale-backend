from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.notifications_handler import (
    TelegramNotificationsHandler,
)


class TelegramNotificationsHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.replies = Mock()
        self.user_context_resolver = Mock()
        self.handler = TelegramNotificationsHandler(
            client=self.client,
            replies=self.replies,
            user_context_resolver=self.user_context_resolver,
        )
        self.channel = SimpleNamespace(
            pk=5,
            is_active=True,
        )
        self.user_context = SimpleNamespace(
            user=SimpleNamespace(pk=7),
            channel=self.channel,
            telegram_chat_id="123",
        )
        self.user_context_resolver.resolve.return_value = (
            self.user_context
        )
        self.settings = SimpleNamespace(
            is_active=True,
            supported_alert_types=(AlertType.PRICE_DROPPED,),
            allows_alert_type=lambda alert_type: True,
        )

    @patch(
        "app.api.v1.notifications.telegram.notifications_handler."
        "get_telegram_channel_settings"
    )
    def test_notifications_command_sends_settings(
        self,
        get_settings_mock,
    ) -> None:
        get_settings_mock.return_value = self.settings

        self.handler.handle_command(
            user_context=self.user_context,
        )

        self.replies.send_message.assert_called_once()
        call = self.replies.send_message.call_args.kwargs
        self.assertEqual(call["chat_id"], "123")
        self.assertIn("Глобальные настройки", call["text"])

    @patch(
        "app.api.v1.notifications.telegram.notifications_handler."
        "toggle_telegram_channel_alert_type"
    )
    def test_type_callback_updates_settings(
        self,
        toggle_mock,
    ) -> None:
        toggle_mock.return_value = self.settings

        self.handler.handle(
            callback_query=self._callback("ng:t:pd")
        )

        toggle_mock.assert_called_once_with(
            user=self.user_context.user,
            telegram_chat_id="123",
            alert_type=AlertType.PRICE_DROPPED,
        )
        self.client.edit_message_text.assert_called_once()

    @patch(
        "app.api.v1.notifications.telegram.notifications_handler."
        "get_telegram_delivery_history"
    )
    def test_history_callback_renders_deliveries(
        self,
        get_history_mock,
    ) -> None:
        get_history_mock.return_value = SimpleNamespace(
            deliveries=(),
        )

        self.handler.handle(
            callback_query=self._callback("ng:h")
        )

        get_history_mock.assert_called_once_with(
            user=self.user_context.user,
            channel=self.channel,
            limit=10,
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
