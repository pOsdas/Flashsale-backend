from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from app.api.v1.monitoring.models import AlertType
from app.api.v1.notifications.services.channel_settings_service import (
    TelegramChannelValidationError,
    set_telegram_channel_active,
    toggle_telegram_channel_alert_type,
)


class TelegramChannelSettingsServiceTests(TestCase):
    @patch(
        "app.api.v1.notifications.services.channel_settings_service."
        "_get_channel"
    )
    def test_disabling_one_type_stores_explicit_allow_list(
        self,
        get_channel_mock,
    ) -> None:
        channel = Mock(
            is_active=True,
            enabled_alert_types=[],
        )
        get_channel_mock.return_value = channel

        result = toggle_telegram_channel_alert_type(
            user=object(),
            telegram_chat_id="123",
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertNotIn(
            AlertType.PRICE_DROPPED,
            result.enabled_alert_types,
        )
        self.assertTrue(channel.enabled_alert_types)
        channel.save.assert_called_once()

    @patch(
        "app.api.v1.notifications.services.channel_settings_service."
        "_get_channel"
    )
    def test_last_enabled_type_cannot_be_disabled(
        self,
        get_channel_mock,
    ) -> None:
        channel = SimpleNamespace(
            is_active=True,
            enabled_alert_types=[AlertType.PRICE_DROPPED],
        )
        get_channel_mock.return_value = channel

        with self.assertRaises(TelegramChannelValidationError):
            toggle_telegram_channel_alert_type(
                user=object(),
                telegram_chat_id="123",
                alert_type=AlertType.PRICE_DROPPED,
            )

    @patch(
        "app.api.v1.notifications.services.channel_settings_service."
        "_get_channel"
    )
    def test_global_active_state_is_updated(
        self,
        get_channel_mock,
    ) -> None:
        channel = Mock(
            is_active=True,
            enabled_alert_types=[],
        )
        get_channel_mock.return_value = channel

        result = set_telegram_channel_active(
            user=object(),
            telegram_chat_id="123",
            is_active=False,
        )

        self.assertFalse(result.is_active)
        channel.save.assert_called_once()
