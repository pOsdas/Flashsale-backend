from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.target_alert_settings_handler import (
    TelegramTargetAlertSettingsHandler,
)


class TelegramTargetAlertSettingsHandlerTests(SimpleTestCase):
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
        self.handler = TelegramTargetAlertSettingsHandler(
            client=self.client,
            user_context_resolver=self.user_context_resolver,
            products_handler=self.products_handler,
        )

    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.get_target_alert_settings"
    )
    def test_opens_alert_settings(self, get_settings: Mock) -> None:
        target_id = uuid4()
        target = SimpleNamespace(
            id=target_id,
            title="Товар",
            external_id="",
            url="https://example.com",
        )
        rules = [
            SimpleNamespace(
                alert_type=AlertType.PRICE_DROPPED,
                threshold_percent=None,
                threshold_absolute=None,
                cooldown_minutes=360,
                is_enabled=True,
            )
        ]
        get_settings.return_value = (target, rules)

        self.handler.handle(
            callback_query=self._callback(
                f"ta:o:{target_id}:1"
            )
        )

        get_settings.assert_called_once_with(
            user=self.user,
            target_id=target_id,
        )
        self.client.edit_message_text.assert_called_once()

    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.get_target_alert_settings"
    )
    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.set_target_alert_rule_enabled"
    )
    def test_sets_alert_rule_state(
        self,
        set_rule: Mock,
        get_settings: Mock,
    ) -> None:
        target_id = uuid4()
        target = SimpleNamespace(
            id=target_id,
            title="Товар",
            external_id="",
            url="https://example.com",
        )
        rule = SimpleNamespace(
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=None,
            threshold_absolute=None,
            cooldown_minutes=360,
            is_enabled=False,
        )
        set_rule.return_value = SimpleNamespace(
            rule=rule,
            changed=True,
        )
        get_settings.return_value = (target, [rule])

        self.handler.handle(
            callback_query=self._callback(
                f"ta:s:pd:0:{target_id}:1"
            )
        )

        set_rule.assert_called_once_with(
            user=self.user,
            target_id=target_id,
            alert_type=AlertType.PRICE_DROPPED,
            is_enabled=False,
        )

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
