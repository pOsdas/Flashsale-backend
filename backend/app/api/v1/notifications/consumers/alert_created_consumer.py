from typing import Any

from django.db import transaction

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
            raise ValueError("alert_created payload does not contain alert_id")

        alert = self._get_alert(alert_id=alert_id)

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

    def _get_alert(self, alert_id: int | str) -> Alert:
        try:
            normalized_alert_id = int(alert_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid alert_id: {alert_id}") from exc

        with transaction.atomic():
            alert = (
                Alert.objects.select_related(
                    "user",
                    "target",
                    "snapshot",
                )
                .filter(id=normalized_alert_id)
                .first()
            )

        if alert is None:
            raise Alert.DoesNotExist(f"Alert with id={normalized_alert_id} does not exist")

        return alert
