from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.api.v1.monitoring.models import Alert, MonitoringTarget, ProductSnapshot
from app.api.v1.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
)
from app.api.v1.notifications.services.notification_service import NotificationService
from app.api.v1.notifications.services.telegram_delivery import TelegramDeliveryError


class NotificationServiceTests(TestCase):
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
            dedup_key="test-became-available-alert",
        )

    def test_send_alert_created_notifications_creates_sent_delivery(self):
        channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

        telegram_adapter = Mock()
        telegram_adapter.send_message.return_value = None

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(len(deliveries), 1)

        delivery = deliveries[0]
        delivery.refresh_from_db()

        self.assertEqual(delivery.user, self.user)
        self.assertEqual(delivery.channel, channel)
        self.assertEqual(delivery.alert, self.alert)
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(delivery.error, "")
        self.assertIsNotNone(delivery.sent_at)
        self.assertIn("Apple iPhone 15 Pro", delivery.message_text)

        telegram_adapter.send_message.assert_called_once_with(
            chat_id="123456789",
            text=delivery.message_text,
        )

    def test_send_alert_created_notifications_skips_inactive_channel(self):
        NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=False,
        )

        telegram_adapter = Mock()

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(deliveries, [])

        deliveries_count = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).count()

        self.assertEqual(deliveries_count, 0)
        telegram_adapter.send_message.assert_not_called()

    def test_send_alert_created_notifications_skips_channel_without_telegram_chat_id(self):
        NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

        telegram_adapter = Mock()

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(deliveries, [])

        deliveries_count = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).count()

        self.assertEqual(deliveries_count, 0)
        telegram_adapter.send_message.assert_not_called()

    def test_send_alert_created_notifications_skips_disabled_alert_type(self):
        NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[
                "price_changed",
            ],
            is_active=True,
        )

        telegram_adapter = Mock()

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(deliveries, [])

        deliveries_count = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).count()

        self.assertEqual(deliveries_count, 0)
        telegram_adapter.send_message.assert_not_called()

    def test_send_alert_created_notifications_sends_when_enabled_alert_types_is_empty(self):
        channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[],
            is_active=True,
        )

        telegram_adapter = Mock()
        telegram_adapter.send_message.return_value = None

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(len(deliveries), 1)

        delivery = deliveries[0]
        delivery.refresh_from_db()

        self.assertEqual(delivery.channel, channel)
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(delivery.error, "")
        self.assertIsNotNone(delivery.sent_at)

        telegram_adapter.send_message.assert_called_once_with(
            chat_id="123456789",
            text=delivery.message_text,
        )

    def test_send_alert_created_notifications_creates_failed_delivery_when_telegram_fails(self):
        channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

        telegram_adapter = Mock()
        telegram_adapter.send_message.side_effect = TelegramDeliveryError(
            "Telegram request timeout"
        )

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(len(deliveries), 1)

        delivery = deliveries[0]
        delivery.refresh_from_db()

        self.assertEqual(delivery.user, self.user)
        self.assertEqual(delivery.channel, channel)
        self.assertEqual(delivery.alert, self.alert)
        self.assertEqual(delivery.status, NotificationDelivery.Status.FAILED)
        self.assertEqual(delivery.error, "Telegram request timeout")
        self.assertIsNone(delivery.sent_at)
        self.assertIn("Apple iPhone 15 Pro", delivery.message_text)

        telegram_adapter.send_message.assert_called_once_with(
            chat_id="123456789",
            text=delivery.message_text,
        )

    def test_send_alert_created_notifications_sends_to_multiple_active_channels(self):
        first_channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="111111111",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

        second_channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="222222222",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

        telegram_adapter = Mock()
        telegram_adapter.send_message.return_value = None

        service = NotificationService(
            telegram_adapter=telegram_adapter,
        )

        deliveries = service.send_alert_created_notifications(self.alert)

        self.assertEqual(len(deliveries), 2)

        deliveries_from_db = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).order_by("channel_id")

        self.assertEqual(deliveries_from_db.count(), 2)

        channel_ids = {
            delivery.channel_id
            for delivery in deliveries_from_db
        }

        self.assertEqual(
            channel_ids,
            {
                first_channel.id,
                second_channel.id,
            },
        )

        for delivery in deliveries_from_db:
            self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
            self.assertEqual(delivery.error, "")
            self.assertIsNotNone(delivery.sent_at)

        self.assertEqual(telegram_adapter.send_message.call_count, 2)

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
