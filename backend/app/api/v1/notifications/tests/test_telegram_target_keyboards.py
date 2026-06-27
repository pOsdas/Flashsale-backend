from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.keyboards import (
    build_target_alert_rule_detail_keyboard,
    build_target_alert_settings_keyboard,
    build_target_history_keyboard,
    build_target_interval_keyboard,
)


class TelegramTargetKeyboardsTests(SimpleTestCase):
    def test_all_callback_data_fit_telegram_limit(self) -> None:
        target_id = str(uuid4())
        rules = [
            SimpleNamespace(
                alert_type=AlertType.REVIEWS_COUNT_CHANGED,
                threshold_percent=None,
                threshold_absolute=Decimal("10.00"),
                cooldown_minutes=360,
                is_enabled=True,
            )
        ]
        keyboards = (
            build_target_alert_settings_keyboard(
                target_id=target_id,
                page=999,
                rules=rules,
            ),
            build_target_alert_rule_detail_keyboard(
                target_id=target_id,
                page=999,
                rule=rules[0],
            ),
            build_target_interval_keyboard(
                target_id=target_id,
                page=999,
                current_interval_minutes=60,
            ),
            build_target_history_keyboard(
                target_id=target_id,
                page=999,
            ),
        )

        for keyboard in keyboards:
            for row in keyboard["inline_keyboard"]:
                for button in row:
                    callback_data = button["callback_data"]
                    self.assertLessEqual(
                        len(callback_data.encode("utf-8")),
                        64,
                    )

    def test_rule_detail_marks_current_threshold_and_cooldown(self) -> None:
        keyboard = build_target_alert_rule_detail_keyboard(
            target_id=str(uuid4()),
            page=1,
            rule=SimpleNamespace(
                alert_type=AlertType.PRICE_DROPPED,
                threshold_percent=Decimal("5.00"),
                threshold_absolute=None,
                cooldown_minutes=360,
                is_enabled=True,
            ),
        )

        texts = [
            button["text"]
            for row in keyboard["inline_keyboard"]
            for button in row
        ]

        self.assertIn("✅ Порог 5%", texts)
        self.assertIn("✅ Тишина: 6 часов", texts)
