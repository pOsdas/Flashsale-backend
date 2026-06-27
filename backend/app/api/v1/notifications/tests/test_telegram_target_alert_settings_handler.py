from decimal import Decimal
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
        target = self._target(target_id)
        rules = [self._price_rule()]
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
    def test_opens_one_rule_detail(self, get_settings: Mock) -> None:
        target_id = uuid4()
        rule = self._price_rule()
        get_settings.return_value = (
            self._target(target_id),
            [rule],
        )

        self.handler.handle(
            callback_query=self._callback(
                f"ta:d:pd:{target_id}:1"
            )
        )

        call = self.client.edit_message_text.call_args.kwargs
        self.assertIn("Настройка уведомления", call["text"])
        self.assertIn("Порог: 5%", call["text"])

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
        target = self._target(target_id)
        rule = self._price_rule(is_enabled=False)
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

    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.get_target_alert_settings"
    )
    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.set_target_alert_rule_threshold"
    )
    def test_sets_price_threshold_and_returns_to_detail(
        self,
        set_threshold: Mock,
        get_settings: Mock,
    ) -> None:
        target_id = uuid4()
        rule = self._price_rule(
            threshold_percent=Decimal("10.00"),
        )
        set_threshold.return_value = SimpleNamespace(
            rule=rule,
            changed=True,
        )
        get_settings.return_value = (
            self._target(target_id),
            [rule],
        )

        self.handler.handle(
            callback_query=self._callback(
                f"ta:t:pd:10:{target_id}:1"
            )
        )

        set_threshold.assert_called_once_with(
            user=self.user,
            target_id=target_id,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("10.00"),
            threshold_absolute=None,
        )
        call = self.client.edit_message_text.call_args.kwargs
        self.assertIn("Порог: 10%", call["text"])

    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.get_target_alert_settings"
    )
    @patch(
        "app.api.v1.notifications.telegram."
        "target_alert_settings_handler.set_target_alert_rule_cooldown"
    )
    def test_sets_cooldown_and_returns_to_detail(
        self,
        set_cooldown: Mock,
        get_settings: Mock,
    ) -> None:
        target_id = uuid4()
        rule = self._price_rule(cooldown_minutes=1440)
        set_cooldown.return_value = SimpleNamespace(
            rule=rule,
            changed=True,
        )
        get_settings.return_value = (
            self._target(target_id),
            [rule],
        )

        self.handler.handle(
            callback_query=self._callback(
                f"ta:c:pd:1440:{target_id}:1"
            )
        )

        set_cooldown.assert_called_once_with(
            user=self.user,
            target_id=target_id,
            alert_type=AlertType.PRICE_DROPPED,
            cooldown_minutes=1440,
        )
        call = self.client.edit_message_text.call_args.kwargs
        self.assertIn("Период тишины: 1 день", call["text"])

    @staticmethod
    def _target(target_id):
        return SimpleNamespace(
            id=target_id,
            title="Товар",
            external_id="",
            url="https://example.com",
        )

    @staticmethod
    def _price_rule(
        *,
        is_enabled: bool = True,
        threshold_percent: Decimal = Decimal("5.00"),
        cooldown_minutes: int = 360,
    ):
        return SimpleNamespace(
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=threshold_percent,
            threshold_absolute=None,
            cooldown_minutes=cooldown_minutes,
            is_enabled=is_enabled,
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
