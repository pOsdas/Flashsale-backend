from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.target_interval_handler import (
    TelegramTargetIntervalHandler,
)


class TelegramTargetIntervalHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.user_context_resolver = Mock()
        self.products_handler = Mock()
        self.user = SimpleNamespace(pk=1)
        self.user_context = SimpleNamespace(
            user=self.user,
            telegram_chat_id="123",
        )
        self.user_context_resolver.resolve.return_value = self.user_context
        self.handler = TelegramTargetIntervalHandler(
            client=self.client,
            user_context_resolver=self.user_context_resolver,
            products_handler=self.products_handler,
        )

    @patch(
        "app.api.v1.notifications.telegram."
        "target_interval_handler.get_monitoring_target_for_user"
    )
    @patch(
        "app.api.v1.notifications.telegram."
        "target_interval_handler.update_monitoring_target"
    )
    def test_sets_supported_interval(
        self,
        update_target: Mock,
        get_target: Mock,
    ) -> None:
        target_id = uuid4()
        get_target.return_value = SimpleNamespace(
            id=target_id,
            title="Товар",
            external_id="",
            url="https://example.com",
            check_interval_minutes=180,
        )

        self.handler.handle(
            callback_query=self._callback(
                f"ti:s:180:{target_id}:1"
            )
        )

        update_target.assert_called_once_with(
            user=self.user,
            target_id=target_id,
            validated_data={
                "check_interval_minutes": 180,
            },
        )

    def test_rejects_interval_below_sixty_minutes(self) -> None:
        target_id = uuid4()

        self.handler.handle(
            callback_query=self._callback(
                f"ti:s:30:{target_id}:1"
            )
        )

        self.client.answer_callback_query.assert_called_once()
        self.client.edit_message_text.assert_not_called()

    @staticmethod
    def _callback(data: str) -> dict:
        return {
            "id": "callback-1",
            "from": {"id": 123},
            "message": {
                "message_id": 10,
                "chat": {"id": 123},
            },
            "data": data,
        }
