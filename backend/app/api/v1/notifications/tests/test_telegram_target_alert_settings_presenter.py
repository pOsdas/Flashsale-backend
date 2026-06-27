from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.target_alert_settings_presenter import (
    build_target_alert_rule_detail_text,
)


class TelegramTargetAlertSettingsPresenterTests(SimpleTestCase):
    def test_builds_price_rule_detail(self) -> None:
        text = build_target_alert_rule_detail_text(
            target=SimpleNamespace(
                title="Товар",
                external_id="",
                url="https://example.com",
            ),
            rule=SimpleNamespace(
                alert_type=AlertType.PRICE_DROPPED,
                threshold_percent=Decimal("5.00"),
                threshold_absolute=None,
                cooldown_minutes=360,
                is_enabled=True,
            ),
        )

        self.assertIn("Правило: Снижение цены", text)
        self.assertIn("Порог: 5%", text)
        self.assertIn("Период тишины: 6 часов", text)

    def test_non_numeric_rule_has_no_threshold(self) -> None:
        text = build_target_alert_rule_detail_text(
            target=SimpleNamespace(
                title="Товар",
                external_id="",
                url="https://example.com",
            ),
            rule=SimpleNamespace(
                alert_type=AlertType.BECAME_AVAILABLE,
                threshold_percent=None,
                threshold_absolute=None,
                cooldown_minutes=0,
                is_enabled=True,
            ),
        )

        self.assertIn("Порог: не используется", text)
        self.assertIn("Период тишины: без паузы", text)
