from typing import Any
from uuid import UUID

from django.db import DatabaseError

from app.api.v1.monitoring.models import Alert
from app.api.v1.notifications.services.notification_service import NotificationService
from app.core.logging import get_logger


logger = get_logger(__name__)


class AlertCreatedNotificationConsumer:
    """
    Consumer для события alert_created.

    Его задача:
    1. Получить alert_id из payload.
    2. Найти Alert в базе.
    3. Отправить уведомления пользователю через доступные каналы.
    4. Не знать ничего про RabbitMQ напрямую.

    RabbitMQ / Outbox Worker просто вызывает этот consumer,
    а consumer уже занимается бизнес-логикой уведомлений.
    """

    def __init__(
        self,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.notification_service = notification_service or NotificationService()

    def handle(self, payload: dict[str, Any]) -> None:
        alert_id = payload.get("alert_id")

        if not alert_id:
            logger.warning(
                "Alert created payload does not contain alert_id",
                extra={
                    "service": "alert_created_notification_consumer",
                    "payload": payload,
                },
            )
            return

        alert = self._get_alert(alert_id=alert_id)

        if alert is None:
            return

        logger.info(
            "Processing alert.created notification",
            extra={
                "service": "alert_created_notification_consumer",
                "alert_id": str(alert.id),
                "user_id": str(alert.user_id),
                "target_id": str(alert.target_id),
            },
        )

        deliveries = self.notification_service.send_alert_created_notifications(
            alert=alert,
        )

        logger.info(
            "Alert notification processing finished",
            extra={
                "service": "alert_created_notification_consumer",
                "alert_id": str(alert.id),
                "user_id": str(alert.user_id),
                "deliveries_count": len(deliveries),
            },
        )

    def _get_alert(self, *, alert_id):
        normalized_alert_id = self._normalize_alert_id(alert_id=alert_id)

        if normalized_alert_id is None:
            return None

        try:
            return (
                Alert.objects
                .select_related(
                    "user",
                    "target",
                    "snapshot",
                )
                .get(id=normalized_alert_id)
            )

        except Alert.DoesNotExist:
            logger.warning(
                "Alert from alert created payload was not found",
                extra={
                    "service": "alert_created_notification_consumer",
                    "alert_id": str(alert_id),
                },
            )
            return None

        except DatabaseError:
            logger.exception(
                "Database error while loading alert for notification",
                extra={
                    "service": "alert_created_notification_consumer",
                    "alert_id": str(alert_id),
                },
            )
            return None

    def _normalize_alert_id(self, *, alert_id):
        try:
            return UUID(str(alert_id))

        except ValueError:
            logger.warning(
                "Invalid alert_id in alert created payload",
                extra={
                    "service": "alert_created_notification_consumer",
                    "alert_id": str(alert_id),
                },
            )
            return None
