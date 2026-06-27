from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContextResolver,
)


class TelegramUserContextResolverTests(SimpleTestCase):
    @patch(
        "app.api.v1.notifications.telegram.user_context."
        "NotificationChannel.objects"
    )
    def test_inactive_notification_channel_still_resolves_user(
        self,
        objects_mock,
    ) -> None:
        queryset = Mock()
        objects_mock.select_related.return_value = queryset
        queryset.filter.return_value = queryset
        queryset.order_by.return_value = queryset
        channel = SimpleNamespace(
            user=SimpleNamespace(pk=7),
            is_active=False,
        )
        queryset.first.return_value = channel

        result = TelegramUserContextResolver().resolve(
            telegram_chat_id="123",
        )

        self.assertIsNotNone(result)
        filter_kwargs = queryset.filter.call_args.kwargs
        self.assertNotIn("is_active", filter_kwargs)
        self.assertEqual(result.channel, channel)
