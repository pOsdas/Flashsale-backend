from decimal import Decimal

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.target_alert_rule_options import (
    get_threshold_kind,
    get_threshold_option_by_code,
    get_threshold_options,
)


class TelegramTargetAlertRuleOptionsTests(SimpleTestCase):
    def test_price_uses_percent_threshold(self) -> None:
        self.assertEqual(
            get_threshold_kind(alert_type=AlertType.PRICE_DROPPED),
            "percent",
        )
        option = get_threshold_option_by_code(
            alert_type=AlertType.PRICE_DROPPED,
            code="10",
        )
        self.assertIsNotNone(option)
        self.assertEqual(option.value, Decimal("10.00"))

    def test_rating_uses_absolute_threshold(self) -> None:
        self.assertEqual(
            get_threshold_kind(alert_type=AlertType.RATING_CHANGED),
            "absolute",
        )

    def test_availability_has_no_threshold_options(self) -> None:
        self.assertIsNone(
            get_threshold_kind(alert_type=AlertType.BECAME_AVAILABLE)
        )
        self.assertEqual(
            get_threshold_options(alert_type=AlertType.BECAME_AVAILABLE),
            (),
        )
