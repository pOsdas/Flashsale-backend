from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.api.v1.monitoring.models import Alert, MonitoringTarget, ProductSnapshot
from app.api.v1.notifications.consumers.alert_created_consumer import (
    AlertCreatedNotificationConsumer,
)


class AlertCreatedNotificationConsumerTests(TestCase):
    def setUp(self):
        self.user = self._create_user(
            email="user@example.com",
            username="user",
            password="password123",
        )

        self.target = MonitoringTarget.objects.create(
            user=self.user,
            marketplace="wb",
            role="competitor",
            url="https://www.wildberries.ru/catalog/123456789/detail.aspx",
            external_id="123456789",
            title="Apple iPhone 15 Pro",
            seller_name="Test Seller",
            brand="Apple",
            check_interval_minutes=60,
            is_active=True,
            last_error="",
            next_check_at=timezone.now(),
        )

        self.snapshot = ProductSnapshot.objects.create(
            target=self.target,
            parse_status="success",
            price=10000000,
            old_price=12000000,
            currency="RUB",
            is_available=True,
            rating=4.8,
            reviews_count=100,
            title="Apple iPhone 15 Pro",
            seller_name="Test Seller",
            brand="Apple",
            raw_data={
                "source": "test",
            },
            error_message="",
            checked_at=timezone.now(),
        )

        self.alert = Alert.objects.create(
            user=self.user,
            target=self.target,
            snapshot=self.snapshot,
            alert_type="became_available",
            severity="medium",
            status="new",
            title="Товар снова доступен",
            message="Товар Apple iPhone 15 Pro снова появился в наличии",
            old_value={
                "is_available": False,
            },
            new_value={
                "is_available": True,
            },
            dedup_key="test-alert-created-consumer-alert",
        )

    def test_handle_calls_notification_service_for_existing_alert(self):
        payload = {
            "alert_id": str(self.alert.id),
        }

        notification_service = Mock()
        notification_service.send_alert_created_notifications.return_value = []

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        consumer.handle(payload)

        notification_service.send_alert_created_notifications.assert_called_once_with(
            alert=self.alert,
        )

    def test_handle_accepts_payload_with_extra_fields(self):
        payload = {
            "alert_id": str(self.alert.id),
            "user_id": str(self.user.id),
            "target_id": str(self.target.id),
            "event": "alert.created",
        }

        notification_service = Mock()
        notification_service.send_alert_created_notifications.return_value = []

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        consumer.handle(payload)

        notification_service.send_alert_created_notifications.assert_called_once_with(
            alert=self.alert,
        )

    def test_handle_does_not_call_notification_service_without_alert_id(self):
        payload = {
            "user_id": str(self.user.id),
            "target_id": str(self.target.id),
        }

        notification_service = Mock()

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        consumer.handle(payload)

        notification_service.send_alert_created_notifications.assert_not_called()

    def test_handle_does_not_call_notification_service_for_empty_alert_id(self):
        payload = {
            "alert_id": "",
        }

        notification_service = Mock()

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        consumer.handle(payload)

        notification_service.send_alert_created_notifications.assert_not_called()

    def test_handle_does_not_call_notification_service_for_unknown_alert_id(self):
        payload = {
            "alert_id": "00000000-0000-0000-0000-000000000000",
        }

        notification_service = Mock()

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        consumer.handle(payload)

        notification_service.send_alert_created_notifications.assert_not_called()

    def test_handle_does_not_raise_error_for_invalid_alert_id(self):
        payload = {
            "alert_id": "invalid-alert-id",
        }

        notification_service = Mock()

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        try:
            consumer.handle(payload)
        except Exception as exc:
            self.fail(
                f"AlertCreatedNotificationConsumer.handle() не должен падать "
                f"на невалидном alert_id, но получил ошибку: {exc}"
            )

        notification_service.send_alert_created_notifications.assert_not_called()

    def test_handle_does_not_raise_error_for_empty_payload(self):
        payload = {}

        notification_service = Mock()

        consumer = AlertCreatedNotificationConsumer(
            notification_service=notification_service,
        )

        try:
            consumer.handle(payload)
        except Exception as exc:
            self.fail(
                f"AlertCreatedNotificationConsumer.handle() не должен падать "
                f"на пустом payload, но получил ошибку: {exc}"
            )

        notification_service.send_alert_created_notifications.assert_not_called()

    def _create_user(self, *, email, username, password):
        User = get_user_model()

        username_field = User.USERNAME_FIELD

        user_data = {
            "email": email,
        }

        if username_field == "username":
            user_data["username"] = username
        else:
            user_data[username_field] = email

            if hasattr(User, "username"):
                user_data["username"] = username

        return User.objects.create_user(
            password=password,
            **user_data,
        )
