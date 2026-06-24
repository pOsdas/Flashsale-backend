from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.notifications.services.telegram_onboarding import (
    TelegramOnboardingError,
)
from app.api.v1.notifications.telegram.start_handler import (
    MESSAGE_ALREADY_CONNECTED,
    MESSAGE_CONNECT_ERROR_SUFFIX,
    MESSAGE_CONNECT_SUCCESS,
    MESSAGE_START_WITHOUT_TOKEN,
    TelegramStartHandler,
)


class TelegramStartHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.replies = Mock()
        self.user_context_resolver = Mock()
        self.handler = TelegramStartHandler(
            replies=self.replies,
            user_context_resolver=self.user_context_resolver,
        )

    def test_start_without_token_for_connected_user(self) -> None:
        self.user_context_resolver.resolve.return_value = (
            SimpleNamespace(user=object())
        )

        self.handler.handle(
            chat_id="123",
            token=None,
        )

        self.replies.send_message.assert_called_once_with(
            chat_id="123",
            text=MESSAGE_ALREADY_CONNECTED,
        )

    def test_start_without_token_for_unconnected_user(self) -> None:
        self.user_context_resolver.resolve.return_value = None

        self.handler.handle(
            chat_id="123",
            token=None,
        )

        self.replies.send_message.assert_called_once_with(
            chat_id="123",
            text=MESSAGE_START_WITHOUT_TOKEN,
        )

    @patch(
        "app.api.v1.notifications.telegram.start_handler."
        "TelegramOnboardingService.connect_chat"
    )
    def test_start_with_valid_token_connects_chat(
        self,
        connect_chat_mock,
    ) -> None:
        connect_chat_mock.return_value = SimpleNamespace(
            id=10,
            user_id=20,
        )

        self.handler.handle(
            chat_id="123",
            token="signed-token",
        )

        connect_chat_mock.assert_called_once_with(
            token="signed-token",
            telegram_chat_id="123",
        )
        self.replies.send_message.assert_called_once_with(
            chat_id="123",
            text=MESSAGE_CONNECT_SUCCESS,
        )

    @patch(
        "app.api.v1.notifications.telegram.start_handler."
        "TelegramOnboardingService.connect_chat"
    )
    def test_start_with_invalid_token_returns_error(
        self,
        connect_chat_mock,
    ) -> None:
        connect_chat_mock.side_effect = TelegramOnboardingError(
            "Некорректная ссылка подключения."
        )

        self.handler.handle(
            chat_id="123",
            token="invalid-token",
        )

        self.replies.send_message.assert_called_once_with(
            chat_id="123",
            text=(
                "Некорректная ссылка подключения.\n\n"
                f"{MESSAGE_CONNECT_ERROR_SUFFIX}"
            ),
        )
