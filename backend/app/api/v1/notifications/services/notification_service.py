from django.db import transaction
from django.utils import timezone

from app.api.v1.notifications.models import NotificationChannel, NotificationDelivery
from app.api.v1.notifications.notification_metrics import NOTIFICATION_DELIVERIES_TOTAL
from app.api.v1.notifications.services.notification_builder import AlertNotificationBuilder
from app.api.v1.notifications.services.telegram_delivery import (
    TelegramDeliveryAdapter,
    TelegramDeliveryError,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class NotificationService:
    def __init__(
        self,
        telegram_adapter: TelegramDeliveryAdapter | None = None,
    ) -> None:
        self.telegram_adapter = telegram_adapter or TelegramDeliveryAdapter()

    def send_alert_created_notifications(self, alert) -> list[NotificationDelivery]:
        channels = NotificationChannel.objects.filter(
            user=alert.user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            is_active=True,
        ).exclude(
            telegram_chat_id="",
        )

        deliveries: list[NotificationDelivery] = []

        if not channels.exists():
            logger.info(
                "No active Telegram notification channels found for alert",
                extra={
                    "service": "notification_service",
                    "alert_id": str(alert.id),
                    "user_id": str(alert.user_id),
                },
            )
            NOTIFICATION_DELIVERIES_TOTAL.labels(
                channel=NotificationChannel.ChannelType.TELEGRAM,
                status="skipped",
            ).inc()
            return deliveries

        for channel in channels:
            delivery = self._send_telegram_alert_notification(
                alert=alert,
                channel=channel,
            )
            deliveries.append(delivery)

        return deliveries

    def _send_telegram_alert_notification(
        self,
        alert,
        channel: NotificationChannel,
    ) -> NotificationDelivery:
        message_text = AlertNotificationBuilder.build_telegram_message(alert)

        with transaction.atomic():
            delivery = NotificationDelivery.objects.create(
                user=alert.user,
                channel=channel,
                alert=alert,
                status=NotificationDelivery.Status.PENDING,
                message_text=message_text,
            )

        try:
            self.telegram_adapter.send_message(
                chat_id=channel.telegram_chat_id,
                text=message_text,
            )

        except TelegramDeliveryError as exc:
            logger.exception(
                "Failed to send Telegram notification",
                extra={
                    "service": "notification_service",
                    "alert_id": str(alert.id),
                    "user_id": str(alert.user_id),
                    "channel_id": str(channel.id),
                    "delivery_id": str(delivery.id),
                    "error": str(exc),
                },
            )

            delivery.status = NotificationDelivery.Status.FAILED
            delivery.error = str(exc)
            delivery.save(
                update_fields=[
                    "status",
                    "error",
                    "updated_at",
                ]
            )

            NOTIFICATION_DELIVERIES_TOTAL.labels(
                channel=NotificationChannel.ChannelType.TELEGRAM,
                status=NotificationDelivery.Status.FAILED,
            ).inc()

            return delivery

        delivery.status = NotificationDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.save(
            update_fields=[
                "status",
                "sent_at",
                "updated_at",
            ]
        )

        NOTIFICATION_DELIVERIES_TOTAL.labels(
            channel=NotificationChannel.ChannelType.TELEGRAM,
            status=NotificationDelivery.Status.SENT,
        ).inc()

        logger.info(
            "Telegram notification sent",
            extra={
                "service": "notification_service",
                "alert_id": str(alert.id),
                "user_id": str(alert.user_id),
                "channel_id": str(channel.id),
                "delivery_id": str(delivery.id),
            },
        )

        return delivery
    