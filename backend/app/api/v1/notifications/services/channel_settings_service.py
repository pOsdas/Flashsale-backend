from dataclasses import dataclass
from typing import Any

from django.db import transaction

from app.api.v1.monitoring.services.alert_rule_constants import (
    SUPPORTED_TARGET_ALERT_TYPES,
)
from app.api.v1.notifications.models import NotificationChannel


class TelegramChannelSettingsError(Exception):
    """Base Telegram notification channel settings error."""


class TelegramChannelNotFoundError(TelegramChannelSettingsError):
    """Telegram channel does not exist for this user and chat."""


class TelegramChannelValidationError(TelegramChannelSettingsError):
    """Telegram channel settings update is invalid."""


@dataclass(frozen=True, slots=True)
class TelegramChannelSettings:
    channel: NotificationChannel
    supported_alert_types: tuple[str, ...]
    enabled_alert_types: tuple[str, ...]

    @property
    def is_active(self) -> bool:
        return bool(self.channel.is_active)

    def allows_alert_type(self, alert_type: str) -> bool:
        return alert_type in self.enabled_alert_types


def get_telegram_channel_settings(
    *,
    user: Any,
    telegram_chat_id: int | str,
) -> TelegramChannelSettings:
    channel = _get_channel(
        user=user,
        telegram_chat_id=telegram_chat_id,
    )
    return _build_settings(channel=channel)


def set_telegram_channel_active(
    *,
    user: Any,
    telegram_chat_id: int | str,
    is_active: bool,
) -> TelegramChannelSettings:
    if not isinstance(is_active, bool):
        raise TelegramChannelValidationError(
            "is_active must be a boolean."
        )

    with transaction.atomic():
        channel = _get_channel(
            user=user,
            telegram_chat_id=telegram_chat_id,
            for_update=True,
        )

        if channel.is_active != is_active:
            channel.is_active = is_active
            channel.save(
                update_fields=[
                    "is_active",
                    "updated_at",
                ]
            )

    return _build_settings(channel=channel)


def toggle_telegram_channel_alert_type(
    *,
    user: Any,
    telegram_chat_id: int | str,
    alert_type: str,
) -> TelegramChannelSettings:
    supported_alert_types = tuple(
        SUPPORTED_TARGET_ALERT_TYPES
    )

    if alert_type not in supported_alert_types:
        raise TelegramChannelValidationError(
            "Unsupported Telegram alert type."
        )

    with transaction.atomic():
        channel = _get_channel(
            user=user,
            telegram_chat_id=telegram_chat_id,
            for_update=True,
        )
        enabled_alert_types = set(
            _get_effective_enabled_alert_types(
                channel=channel,
                supported_alert_types=supported_alert_types,
            )
        )

        if alert_type in enabled_alert_types:
            if len(enabled_alert_types) == 1:
                raise TelegramChannelValidationError(
                    "Нельзя отключить последний тип уведомлений. "
                    "Используйте кнопку «Приостановить все»."
                )

            enabled_alert_types.remove(alert_type)
        else:
            enabled_alert_types.add(alert_type)

        ordered_enabled_alert_types = [
            item
            for item in supported_alert_types
            if item in enabled_alert_types
        ]

        if len(ordered_enabled_alert_types) == len(
            supported_alert_types
        ):
            stored_enabled_alert_types: list[str] = []
        else:
            stored_enabled_alert_types = (
                ordered_enabled_alert_types
            )

        channel.enabled_alert_types = (
            stored_enabled_alert_types
        )
        channel.save(
            update_fields=[
                "enabled_alert_types",
                "updated_at",
            ]
        )

    return _build_settings(channel=channel)


def _get_channel(
    *,
    user: Any,
    telegram_chat_id: int | str,
    for_update: bool = False,
) -> NotificationChannel:
    normalized_chat_id = str(telegram_chat_id).strip()

    if not normalized_chat_id:
        raise TelegramChannelValidationError(
            "Telegram chat ID is empty."
        )

    queryset = NotificationChannel.objects.select_related(
        "user"
    )

    if for_update:
        queryset = queryset.select_for_update()

    channel = (
        queryset
        .filter(
            user=user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id=normalized_chat_id,
        )
        .order_by("-updated_at")
        .first()
    )

    if channel is None:
        raise TelegramChannelNotFoundError(
            "Telegram notification channel was not found."
        )

    return channel


def _build_settings(
    *,
    channel: NotificationChannel,
) -> TelegramChannelSettings:
    supported_alert_types = tuple(
        SUPPORTED_TARGET_ALERT_TYPES
    )
    enabled_alert_types = (
        _get_effective_enabled_alert_types(
            channel=channel,
            supported_alert_types=supported_alert_types,
        )
    )

    return TelegramChannelSettings(
        channel=channel,
        supported_alert_types=supported_alert_types,
        enabled_alert_types=enabled_alert_types,
    )


def _get_effective_enabled_alert_types(
    *,
    channel: NotificationChannel,
    supported_alert_types: tuple[str, ...],
) -> tuple[str, ...]:
    configured_alert_types = channel.enabled_alert_types

    if not configured_alert_types:
        return supported_alert_types

    configured_alert_type_set = {
        str(item)
        for item in configured_alert_types
    }

    return tuple(
        alert_type
        for alert_type in supported_alert_types
        if alert_type in configured_alert_type_set
    )
