import json

import httpx
from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.commands import (
    TELEGRAM_BOT_COMMANDS,
)


class TelegramBotClientTests(SimpleTestCase):
    def test_get_updates_requests_messages_and_callbacks(self) -> None:
        captured_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [],
                },
            )

        http_client = httpx.Client(
            base_url="https://api.telegram.org/bottest-token",
            transport=httpx.MockTransport(handler),
        )
        client = TelegramBotClient(
            token="test-token",
            client=http_client,
        )

        result = client.get_updates(offset=10)

        self.assertEqual(result, [])
        self.assertIsNotNone(captured_request)

        query = captured_request.url.params
        allowed_updates = json.loads(query["allowed_updates"])

        self.assertEqual(query["offset"], "10")
        self.assertEqual(
            allowed_updates,
            [
                "message",
                "callback_query",
            ],
        )

        http_client.close()

    def test_set_my_commands_registers_command_menu(self) -> None:
        captured_path = ""
        captured_payload: dict | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_path, captured_payload
            captured_path = request.url.path
            captured_payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": True,
                },
            )

        http_client = httpx.Client(
            base_url="https://api.telegram.org/bottest-token",
            transport=httpx.MockTransport(handler),
        )
        client = TelegramBotClient(
            token="test-token",
            client=http_client,
        )

        result = client.set_my_commands(
            commands=TELEGRAM_BOT_COMMANDS,
        )

        self.assertTrue(result)
        self.assertEqual(captured_path, "/bottest-token/setMyCommands")
        self.assertIsNotNone(captured_payload)
        self.assertEqual(
            captured_payload["commands"],
            list(TELEGRAM_BOT_COMMANDS),
        )

        http_client.close()

    def test_send_message_passes_inline_keyboard(self) -> None:
        captured_payload: dict | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_payload
            captured_payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 1,
                    },
                },
            )

        http_client = httpx.Client(
            base_url="https://api.telegram.org/bottest-token",
            transport=httpx.MockTransport(handler),
        )
        client = TelegramBotClient(
            token="test-token",
            client=http_client,
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "Добавить",
                        "callback_data": "product:add:token",
                    }
                ]
            ]
        }

        client.send_message(
            chat_id="123",
            text="Товар найден",
            reply_markup=reply_markup,
        )

        self.assertIsNotNone(captured_payload)
        self.assertEqual(captured_payload["chat_id"], 123)
        self.assertEqual(
            captured_payload["reply_markup"],
            reply_markup,
        )

        http_client.close()
