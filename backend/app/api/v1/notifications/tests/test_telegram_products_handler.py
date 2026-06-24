from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import MonitoringTargetStatus
from app.api.v1.monitoring.services.target_query_service import (
    MonitoringTargetListItem,
    MonitoringTargetPage,
)
from app.api.v1.notifications.telegram.products_handler import (
    MESSAGE_SETTINGS_NOT_AVAILABLE,
    TelegramProductsHandler,
)


class TelegramProductsHandlerTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.replies = Mock()
        self.user = SimpleNamespace(pk=7)
        self.user_context = SimpleNamespace(
            user=self.user,
            telegram_chat_id="123",
        )
        self.user_context_resolver = Mock()
        self.user_context_resolver.resolve.return_value = (
            self.user_context
        )
        self.handler = TelegramProductsHandler(
            client=self.client,
            replies=self.replies,
            user_context_resolver=self.user_context_resolver,
            page_size=3,
        )
        self.target_id = uuid4()
        self.target = SimpleNamespace(
            id=self.target_id,
            title="Товар",
            external_id="123",
            url="https://www.wildberries.ru/catalog/123/detail.aspx",
            marketplace="wb",
            status=MonitoringTargetStatus.ACTIVE,
            is_active=True,
            check_interval_minutes=60,
        )
        self.target_page = MonitoringTargetPage(
            items=(
                MonitoringTargetListItem(
                    target=self.target,
                    latest_price=Decimal("1000"),
                    latest_currency="RUB",
                    latest_is_available=True,
                    latest_rating=None,
                    latest_reviews_count=None,
                    latest_checked_at=None,
                    latest_parse_status="success",
                    latest_source="cache",
                ),
            ),
            page=1,
            page_size=3,
            total_items=1,
            total_pages=1,
        )

    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "list_monitoring_targets_for_user"
    )
    def test_products_command_sends_page(
        self,
        list_targets_mock,
    ) -> None:
        list_targets_mock.return_value = self.target_page

        self.handler.handle_command(
            user_context=self.user_context,
        )

        self.replies.send_message.assert_called_once()
        call_kwargs = self.replies.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], "123")
        self.assertIn("Товар", call_kwargs["text"])

    def test_settings_callback_returns_next_stage_message(self) -> None:
        self.handler.handle_callback(
            callback_query={
                "id": "callback-1",
                "from": {"id": 123},
                "data": (
                    f"target:settings:{self.target_id}:1"
                ),
                "message": {
                    "message_id": 50,
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                },
            }
        )

        self.client.answer_callback_query.assert_called_once_with(
            callback_query_id="callback-1",
            text=MESSAGE_SETTINGS_NOT_AVAILABLE,
            show_alert=True,
        )

    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "list_monitoring_targets_for_user"
    )
    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "pause_monitoring_target"
    )
    def test_pause_callback_updates_page(
        self,
        pause_target_mock,
        list_targets_mock,
    ) -> None:
        list_targets_mock.return_value = self.target_page

        self.handler.handle_callback(
            callback_query={
                "id": "callback-1",
                "from": {"id": 123},
                "data": f"target:pause:{self.target_id}:1",
                "message": {
                    "message_id": 50,
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                },
            }
        )

        pause_target_mock.assert_called_once_with(
            user=self.user,
            target_id=self.target_id,
        )
        self.client.edit_message_text.assert_called_once()

    @patch(
        "app.api.v1.notifications.telegram.products_handler."
        "get_monitoring_target_for_user"
    )
    def test_delete_ask_shows_confirmation(
        self,
        get_target_mock,
    ) -> None:
        get_target_mock.return_value = self.target

        self.handler.handle_callback(
            callback_query={
                "id": "callback-1",
                "from": {"id": 123},
                "data": f"target:delete:ask:{self.target_id}:1",
                "message": {
                    "message_id": 50,
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                },
            }
        )

        self.client.edit_message_text.assert_called_once()
        edit_kwargs = self.client.edit_message_text.call_args.kwargs
        self.assertIn("Удалить товар", edit_kwargs["text"])
