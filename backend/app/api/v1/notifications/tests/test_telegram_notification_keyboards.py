from types import SimpleNamespace

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.telegram.keyboards import (
    build_existing_product_keyboard,
    build_notification_settings_keyboard,
)


class TelegramNotificationKeyboardsTests(SimpleTestCase):
    def test_global_settings_keyboard_contains_history(self) -> None:
        settings = SimpleNamespace(
            is_active=True,
            supported_alert_types=(AlertType.PRICE_DROPPED,),
            allows_alert_type=lambda alert_type: True,
        )

        keyboard = build_notification_settings_keyboard(
            settings=settings,
        )

        callbacks = [
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
        ]
        self.assertIn("ng:h", callbacks)
        self.assertIn("ng:t:pd", callbacks)

    def test_existing_product_keyboard_opens_products_and_check(self) -> None:
        keyboard = build_existing_product_keyboard(
            target_id="00000000-0000-0000-0000-000000000001",
        )

        callbacks = [
            row[0]["callback_data"]
            for row in keyboard["inline_keyboard"]
        ]
        self.assertEqual(callbacks[0], "products:page:1")
        self.assertTrue(callbacks[1].startswith("target:check:"))
