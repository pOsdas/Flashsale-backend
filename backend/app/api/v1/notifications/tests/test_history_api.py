from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
)


class NotificationDeliveryHistoryAPITests(APITestCase):
    HISTORY_LIST_URL = "/api/v1/notifications/history/"

    def setUp(self):
        self.user = self._create_user(
            email="user@example.com",
            username="user",
            password="password123",
        )
        self.other_user = self._create_user(
            email="other@example.com",
            username="other",
            password="password123",
        )

        self.channel = NotificationChannel.objects.create(
            user=self.user,
            type="telegram",
            telegram_chat_id="123456789",
            is_active=True,
        )

        self.other_channel = NotificationChannel.objects.create(
            user=self.other_user,
            type="telegram",
            telegram_chat_id="987654321",
            is_active=True,
        )

        self.sent_delivery = NotificationDelivery.objects.create(
            user=self.user,
            channel=self.channel,
            status=NotificationDelivery.Status.SENT,
            message_text="Уведомление успешно отправлено",
            error="",
            sent_at=timezone.now(),
        )

        self.failed_delivery = NotificationDelivery.objects.create(
            user=self.user,
            channel=self.channel,
            status=NotificationDelivery.Status.FAILED,
            message_text="Уведомление не отправлено",
            error="Telegram request timeout",
            sent_at=None,
        )

        self.other_delivery = NotificationDelivery.objects.create(
            user=self.other_user,
            channel=self.other_channel,
            status=NotificationDelivery.Status.SENT,
            message_text="Чужое уведомление",
            error="",
            sent_at=timezone.now(),
        )

    def test_history_list_requires_authentication(self):
        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_history_list_returns_only_current_user_deliveries(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(self.sent_delivery.id, returned_ids)
        self.assertIn(self.failed_delivery.id, returned_ids)
        self.assertNotIn(self.other_delivery.id, returned_ids)

    def test_history_list_contains_expected_fields(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.HISTORY_LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        first_item = results[0]

        self.assertIn("id", first_item)
        self.assertIn("status", first_item)
        self.assertIn("channel_id", first_item)
        self.assertIn("channel_type", first_item)
        self.assertIn("channel_is_active", first_item)
        self.assertIn("alert_id", first_item)
        self.assertIn("message_text", first_item)
        self.assertIn("error", first_item)
        self.assertIn("created_at", first_item)
        self.assertIn("updated_at", first_item)
        self.assertIn("sent_at", first_item)

    def test_history_detail_requires_authentication(self):
        url = self._detail_url(self.sent_delivery.id)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_history_detail_returns_current_user_delivery(self):
        self.client.force_authenticate(user=self.user)

        url = self._detail_url(self.sent_delivery.id)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.sent_delivery.id)
        self.assertEqual(response.data["status"], NotificationDelivery.Status.SENT)
        self.assertEqual(response.data["channel_id"], self.channel.id)
        self.assertEqual(response.data["channel_type"], "telegram")
        self.assertEqual(response.data["channel_is_active"], True)
        self.assertEqual(response.data["message_text"], "Уведомление успешно отправлено")
        self.assertEqual(response.data["error"], "")

    def test_history_detail_does_not_return_other_user_delivery(self):
        self.client.force_authenticate(user=self.user)

        url = self._detail_url(self.other_delivery.id)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_list_filter_by_status_sent(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "status": NotificationDelivery.Status.SENT,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.sent_delivery.id)
        self.assertEqual(results[0]["status"], NotificationDelivery.Status.SENT)

    def test_history_list_filter_by_status_failed(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "status": NotificationDelivery.Status.FAILED,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.failed_delivery.id)
        self.assertEqual(results[0]["status"], NotificationDelivery.Status.FAILED)

    def test_history_list_filter_by_channel_id(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "channel_id": str(self.channel.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(self.sent_delivery.id, returned_ids)
        self.assertIn(self.failed_delivery.id, returned_ids)
        self.assertNotIn(self.other_delivery.id, returned_ids)

        for item in results:
            self.assertEqual(item["channel_id"], self.channel.id)

    def test_history_list_filter_by_invalid_channel_id_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "channel_id": "abc",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["details"],
            {
                "channel_id": "channel_id должен быть числом.",
            },
        )

    def test_history_list_filter_by_created_from(self):
        self.client.force_authenticate(user=self.user)

        old_date = timezone.now() - timedelta(days=10)
        fresh_date = timezone.now()

        NotificationDelivery.objects.filter(id=self.failed_delivery.id).update(
            created_at=old_date,
        )
        NotificationDelivery.objects.filter(id=self.sent_delivery.id).update(
            created_at=fresh_date,
        )

        created_from = (timezone.now() - timedelta(days=1)).date().isoformat()

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "created_from": created_from,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(self.sent_delivery.id, returned_ids)
        self.assertNotIn(self.failed_delivery.id, returned_ids)

    def test_history_list_filter_by_created_to(self):
        self.client.force_authenticate(user=self.user)

        old_date = timezone.now() - timedelta(days=10)
        fresh_date = timezone.now()

        NotificationDelivery.objects.filter(id=self.failed_delivery.id).update(
            created_at=old_date,
        )
        NotificationDelivery.objects.filter(id=self.sent_delivery.id).update(
            created_at=fresh_date,
        )

        created_to = (timezone.now() - timedelta(days=5)).date().isoformat()

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "created_to": created_to,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self._get_results(response)
        returned_ids = {item["id"] for item in results}

        self.assertIn(self.failed_delivery.id, returned_ids)
        self.assertNotIn(self.sent_delivery.id, returned_ids)

    def test_history_list_filter_by_invalid_created_from_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "created_from": "11-06-2026",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["details"],
            {
                "created_from": (
                    "Дата должна быть в формате YYYY-MM-DD."
                ),
            },
        )

    def test_history_list_filter_by_invalid_created_to_returns_400(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            self.HISTORY_LIST_URL,
            {
                "created_to": "11-06-2026",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["details"],
            {
                "created_to": (
                    "Дата должна быть в формате YYYY-MM-DD."
                ),
            },
        )

    def _detail_url(self, delivery_id):
        return f"/api/v1/notifications/history/{delivery_id}/"

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