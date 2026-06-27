from dataclasses import dataclass
from typing import Any

from app.api.v1.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
)


DEFAULT_TELEGRAM_DELIVERY_HISTORY_LIMIT = 10
MAX_TELEGRAM_DELIVERY_HISTORY_LIMIT = 20


@dataclass(frozen=True, slots=True)
class TelegramDeliveryHistory:
    channel: NotificationChannel
    deliveries: tuple[NotificationDelivery, ...]


def get_telegram_delivery_history(
    *,
    user: Any,
    channel: NotificationChannel,
    limit: int = DEFAULT_TELEGRAM_DELIVERY_HISTORY_LIMIT,
) -> TelegramDeliveryHistory:
    normalized_limit = max(
        1,
        min(
            int(limit),
            MAX_TELEGRAM_DELIVERY_HISTORY_LIMIT,
        ),
    )

    deliveries = tuple(
        NotificationDelivery.objects
        .filter(
            user=user,
            channel=channel,
        )
        .select_related(
            "alert",
            "alert__target",
        )
        .order_by("-created_at")[:normalized_limit]
    )

    return TelegramDeliveryHistory(
        channel=channel,
        deliveries=deliveries,
    )
