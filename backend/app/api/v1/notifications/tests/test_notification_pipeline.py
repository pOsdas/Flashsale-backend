from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from app.api.v1.monitoring.models import Alert, MonitoringTarget, ProductSnapshot
from app.api.v1.notifications.consumers.alert_created_consumer import (
    AlertCreatedNotificationConsumer,
)
from app.api.v1.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
)
from app.api.v1.notifications.services.telegram_delivery import (
    TelegramDeliveryAdapter,
    TelegramDeliveryError,
)


class NotificationPipelineTests(TestCase):
    HISTORY_LIST_URL = "/api/v1/notifications/history/"

    def setUp(self):
        self.client = APIClient()

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
            dedup_key="test-pipeline-became-available-alert",
        )

        self.channel = NotificationChannel.objects.create(
            user=self.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id="123456789",
            enabled_alert_types=[
                "became_available",
            ],
            is_active=True,
        )

    def test_alert_created_pipeline_creates_delivery_and_history_api_returns_it(self):
        payload = self._build_alert_created_payload(self.alert)

        with patch.object(
            TelegramDeliveryAdapter,
            "send_message",
            return_value=None,
        ) as mocked_send_message:
            self._handle_alert_created_event(payload)

        deliveries = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        )

        self.assertEqual(deliveries.count(), 1)

        delivery = deliveries.first()

        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(delivery.channel, self.channel)
        self.assertEqual(delivery.error, "")
        self.assertIsNotNone(delivery.sent_at)
        self.assertIn("Apple iPhone 15 Pro", delivery.message_text)

        mocked_send_message.assert_called_once_with(
            chat_id="123456789",
            text=delivery.message_text,
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(delivery.id, returned_ids)

        history_item = next(
            item
            for item in results
            if item["id"] == delivery.id
        )

        self.assertEqual(history_item["status"], NotificationDelivery.Status.SENT)
        self.assertEqual(history_item["channel_id"], self.channel.id)
        self.assertEqual(history_item["channel_type"], NotificationChannel.ChannelType.TELEGRAM)
        self.assertEqual(history_item["channel_is_active"], True)
        self.assertEqual(history_item["alert_id"], str(self.alert.id))
        self.assertIn("Apple iPhone 15 Pro", history_item["message_text"])
        self.assertEqual(history_item["error"], "")
        self.assertIsNotNone(history_item["sent_at"])

    def test_alert_created_pipeline_creates_failed_delivery_when_telegram_fails(self):
        payload = self._build_alert_created_payload(self.alert)

        with patch.object(
            TelegramDeliveryAdapter,
            "send_message",
            side_effect=TelegramDeliveryError("Telegram request timeout"),
        ) as mocked_send_message:
            self._handle_alert_created_event(payload)

        deliveries = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        )

        self.assertEqual(deliveries.count(), 1)

        delivery = deliveries.first()

        self.assertEqual(delivery.status, NotificationDelivery.Status.FAILED)
        self.assertEqual(delivery.channel, self.channel)
        self.assertEqual(delivery.error, "Telegram request timeout")
        self.assertIsNone(delivery.sent_at)
        self.assertIn("Apple iPhone 15 Pro", delivery.message_text)

        mocked_send_message.assert_called_once_with(
            chat_id="123456789",
            text=delivery.message_text,
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(delivery.id, returned_ids)

        history_item = next(
            item
            for item in results
            if item["id"] == delivery.id
        )

        self.assertEqual(history_item["status"], NotificationDelivery.Status.FAILED)
        self.assertEqual(history_item["channel_id"], self.channel.id)
        self.assertEqual(history_item["channel_type"], NotificationChannel.ChannelType.TELEGRAM)
        self.assertEqual(history_item["channel_is_active"], True)
        self.assertEqual(history_item["alert_id"], str(self.alert.id))
        self.assertIn("Apple iPhone 15 Pro", history_item["message_text"])
        self.assertEqual(history_item["error"], "Telegram request timeout")
        self.assertIsNone(history_item["sent_at"])

    def test_alert_created_pipeline_does_not_create_delivery_for_disabled_alert_type(self):
        self.channel.enabled_alert_types = [
            "price_changed",
        ]
        self.channel.save(
            update_fields=[
                "enabled_alert_types",
                "updated_at",
            ]
        )

        payload = self._build_alert_created_payload(self.alert)

        with patch.object(
            TelegramDeliveryAdapter,
            "send_message",
            return_value=None,
        ) as mocked_send_message:
            self._handle_alert_created_event(payload)

        deliveries_count = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).count()

        self.assertEqual(deliveries_count, 0)
        mocked_send_message.assert_not_called()

        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)

        self.assertEqual(results, [])

    def test_alert_created_pipeline_does_not_create_delivery_for_inactive_channel(self):
        self.channel.is_active = False
        self.channel.save(
            update_fields=[
                "is_active",
                "updated_at",
            ]
        )

        payload = self._build_alert_created_payload(self.alert)

        with patch.object(
            TelegramDeliveryAdapter,
            "send_message",
            return_value=None,
        ) as mocked_send_message:
            self._handle_alert_created_event(payload)

        deliveries_count = NotificationDelivery.objects.filter(
            user=self.user,
            alert=self.alert,
        ).count()

        self.assertEqual(deliveries_count, 0)
        mocked_send_message.assert_not_called()

        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)

        self.assertEqual(results, [])

    def _build_alert_created_payload(self, alert):
        return {
            "alert_id": str(alert.id),
            "user_id": str(alert.user_id),
            "target_id": str(alert.target_id),
        }

    def _handle_alert_created_event(self, payload):
        consumer = AlertCreatedNotificationConsumer()

        if hasattr(consumer, "handle"):
            return consumer.handle(payload)

        if hasattr(consumer, "consume"):
            return consumer.consume(payload)

        if hasattr(consumer, "process"):
            return consumer.process(payload)

        raise AssertionError(
            "В AlertCreatedNotificationConsumer не найден метод обработки события. "
            "Проверь файл app/api/v1/notifications/consumers/alert_created_consumer.py"
        )

    def _get_results(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]

        return response.data

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
