from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from app.api.v1.notifications.services.telegram_delivery import (
    TelegramDeliveryAdapter,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient


@override_settings(
    NOTIF_TELEGRAM_API_BASE_URL="http://load-simulator:8099",
    NOTIF_TELEGRAM_BOT_TOKEN="test-token",
)
class TelegramBaseURLTests(SimpleTestCase):
    def test_bot_client_uses_configured_base_url(self):
        client = TelegramBotClient(token="test-token", client=Mock())
        self.assertEqual(
            client.base_url,
            "http://load-simulator:8099/bottest-token",
        )

    @patch("app.api.v1.notifications.services.telegram_delivery.httpx.post")
    def test_delivery_adapter_uses_configured_base_url(self, post):
        post.return_value.status_code = 200
        post.return_value.text = '{"ok": true}'
        post.return_value.json.return_value = {"ok": True, "result": {}}

        TelegramDeliveryAdapter().send_message(
            chat_id="load-1",
            text="hello",
        )

        self.assertEqual(
            post.call_args.kwargs["url"],
            "http://load-simulator:8099/bottest-token/sendMessage",
        )
