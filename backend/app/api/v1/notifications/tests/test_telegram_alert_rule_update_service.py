from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.monitoring.services.alert_rule_service import (
    AlertRuleSettingsValidationError,
)
from app.api.v1.monitoring.services.alert_rule_update_service import (
    set_target_alert_rule_cooldown,
    set_target_alert_rule_threshold,
)


class TargetAlertRuleUpdateServiceValidationTests(SimpleTestCase):
    def test_rejects_threshold_for_non_numeric_rule(self) -> None:
        with self.assertRaises(AlertRuleSettingsValidationError):
            set_target_alert_rule_threshold(
                user=object(),
                target_id="00000000-0000-0000-0000-000000000000",
                alert_type=AlertType.BECAME_AVAILABLE,
                threshold_percent="5",
                threshold_absolute=None,
            )

    def test_rejects_cooldown_over_seven_days(self) -> None:
        with self.assertRaises(AlertRuleSettingsValidationError):
            set_target_alert_rule_cooldown(
                user=object(),
                target_id="00000000-0000-0000-0000-000000000000",
                alert_type=AlertType.PRICE_DROPPED,
                cooldown_minutes=10081,
            )
