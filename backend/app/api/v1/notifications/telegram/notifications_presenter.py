from django.utils import timezone

from app.api.v1.notifications.models import NotificationDelivery
from app.api.v1.notifications.services.channel_settings_service import (
    TelegramChannelSettings,
)
from app.api.v1.notifications.services.delivery_query_service import (
    TelegramDeliveryHistory,
)
from app.api.v1.notifications.telegram.target_alert_settings_presenter import (
    ALERT_TYPE_TITLES,
)


DELIVERY_STATUS_TITLES = {
    NotificationDelivery.Status.PENDING: "⏳ Ожидает отправки",
    NotificationDelivery.Status.SENT: "✅ Отправлено",
    NotificationDelivery.Status.FAILED: "❌ Ошибка отправки",
}


def build_notification_settings_text(
    *,
    settings: TelegramChannelSettings,
) -> str:
    global_state = (
        "включены"
        if settings.is_active
        else "приостановлены"
    )
    lines = [
        "🔔 Глобальные настройки Telegram",
        "",
        f"Все уведомления: {global_state}",
        "",
        "Эти настройки действуют сразу для всех товаров.",
        "Индивидуальные правила товара продолжают определять,",
        "должно ли конкретное изменение создать уведомление.",
        "",
    ]

    for alert_type in settings.supported_alert_types:
        state = (
            "✅"
            if settings.allows_alert_type(alert_type)
            else "❌"
        )
        title = ALERT_TYPE_TITLES.get(
            alert_type,
            alert_type,
        )
        lines.append(f"{state} {title}")

    if not settings.is_active:
        lines.extend(
            [
                "",
                "Доставка приостановлена целиком. "
                "Настройки отдельных типов сохранены.",
            ]
        )

    return "\n".join(lines).strip()


def build_notification_delivery_history_text(
    *,
    history: TelegramDeliveryHistory,
) -> str:
    lines = [
        "📨 История доставок",
        "",
    ]

    if not history.deliveries:
        lines.append(
            "Уведомления через этот Telegram-канал ещё не отправлялись."
        )
        return "\n".join(lines)

    for index, delivery in enumerate(
        history.deliveries,
        start=1,
    ):
        status = DELIVERY_STATUS_TITLES.get(
            delivery.status,
            delivery.status,
        )
        alert = delivery.alert
        target = getattr(alert, "target", None)
        target_title = (
            getattr(target, "title", "")
            or getattr(target, "external_id", "")
            or "Неизвестный товар"
        )
        alert_type = getattr(alert, "alert_type", "")
        alert_title = ALERT_TYPE_TITLES.get(
            alert_type,
            getattr(alert, "title", "")
            or "Уведомление",
        )
        event_time = (
            delivery.sent_at
            or delivery.created_at
        )

        lines.extend(
            [
                f"{index}. {status}",
                target_title,
                alert_title,
                _format_datetime(event_time),
            ]
        )

        if delivery.status == NotificationDelivery.Status.FAILED:
            error = _truncate(
                str(delivery.error or "Неизвестная ошибка"),
                140,
            )
            lines.append(f"Причина: {error}")

        if index != len(history.deliveries):
            lines.append("")

    return "\n".join(lines).strip()


def _format_datetime(value) -> str:
    if value is None:
        return "Дата не указана"

    return timezone.localtime(value).strftime(
        "%d.%m.%Y %H:%M"
    )


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= limit:
        return normalized

    return normalized[: limit - 1].rstrip() + "…"
