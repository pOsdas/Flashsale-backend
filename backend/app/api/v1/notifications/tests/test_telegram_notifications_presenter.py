from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.models import NotificationDelivery
from app.api.v1.notifications.telegram.notifications_presenter import (
    build_notification_delivery_history_text,
    build_notification_settings_text,
)


class TelegramNotificationsPresenterTests(SimpleTestCase):
    def test_settings_text_contains_global_state_and_types(self) -> None:
        settings = SimpleNamespace(
            is_active=True,
            supported_alert_types=(
                AlertType.PRICE_DROPPED,
                AlertType.BECAME_AVAILABLE,
            ),
            allows_alert_type=lambda alert_type: (
                alert_type == AlertType.PRICE_DROPPED
            ),
        )

        text = build_notification_settings_text(
            settings=settings,
        )

        self.assertIn("Все уведомления: включены", text)
        self.assertIn("✅ Снижение цены", text)
        self.assertIn("❌ Появление в наличии", text)

    def test_delivery_history_contains_status_and_target(self) -> None:
        alert = SimpleNamespace(
            alert_type=AlertType.PRICE_DROPPED,
            title="Цена снизилась",
            target=SimpleNamespace(
                title="Товар",
                external_id="123",
            ),
        )
        delivery = SimpleNamespace(
            status=NotificationDelivery.Status.SENT,
            alert=alert,
            sent_at=datetime(2026, 6, 27, 12, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 6, 27, 11, 59, tzinfo=timezone.utc),
            error="",
        )
        history = SimpleNamespace(
            deliveries=(delivery,),
        )

        text = build_notification_delivery_history_text(
            history=history,
        )

        self.assertIn("Отправлено", text)
        self.assertIn("Товар", text)
        self.assertIn("Снижение цены", text)
