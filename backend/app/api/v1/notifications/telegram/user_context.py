from dataclasses import dataclass
from typing import Any

from app.api.v1.notifications.models import NotificationChannel


@dataclass(frozen=True, slots=True)
class TelegramUserContext:
    user: Any
    channel: NotificationChannel
    telegram_chat_id: str


class TelegramUserContextResolver:
    def resolve(
        self,
        *,
        telegram_chat_id: int | str,
    ) -> TelegramUserContext | None:
        normalized_chat_id = str(telegram_chat_id).strip()

        if not normalized_chat_id:
            return None

        channel = (
            NotificationChannel.objects
            .select_related("user")
            .filter(
                type=NotificationChannel.ChannelType.TELEGRAM,
                telegram_chat_id=normalized_chat_id,
                user__is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )

        if channel is None:
            return None

        return TelegramUserContext(
            user=channel.user,
            channel=channel,
            telegram_chat_id=normalized_chat_id,
        )
