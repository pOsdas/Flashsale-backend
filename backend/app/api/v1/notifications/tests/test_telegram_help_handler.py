from unittest.mock import Mock

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.commands import HELP_MESSAGE
from app.api.v1.notifications.telegram.help_handler import (
    TelegramHelpHandler,
)


class TelegramHelpHandlerTests(SimpleTestCase):
    def test_help_message_is_sent(self) -> None:
        replies = Mock()
        handler = TelegramHelpHandler(
            replies=replies,
        )

        handler.handle(
            chat_id="123",
        )

        replies.send_message.assert_called_once_with(
            chat_id="123",
            text=HELP_MESSAGE,
        )
