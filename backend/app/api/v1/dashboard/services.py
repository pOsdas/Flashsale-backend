from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q

from app.api.v1.monitoring.models import Alert, MonitoringTarget
from app.api.v1.notifications.models import NotificationChannel, NotificationDelivery


@dataclass(frozen=True)
class DashboardData:
    monitoring_targets_count: int
    active_targets_count: int
    inactive_targets_count: int
    targets_with_errors_count: int

    alerts_count: int
    new_alerts_count: int

    notification_channels_count: int
    active_notification_channels_count: int
    telegram_connected: bool

    notification_deliveries_count: int
    sent_notification_deliveries_count: int
    failed_notification_deliveries_count: int

    last_alert_created_at: datetime | None
    last_notification_delivery_created_at: datetime | None


class DashboardService:
    def get_dashboard(self, *, user) -> DashboardData:
        targets_queryset = MonitoringTarget.objects.filter(
            user=user,
        )

        alerts_queryset = Alert.objects.filter(
            user=user,
        )

        channels_queryset = NotificationChannel.objects.filter(
            user=user,
        )

        deliveries_queryset = NotificationDelivery.objects.filter(
            user=user,
        )

        last_alert = (
            alerts_queryset
            .order_by("-created_at")
            .first()
        )

        last_delivery = (
            deliveries_queryset
            .order_by("-created_at")
            .first()
        )

        telegram_connected = channels_queryset.filter(
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id__isnull=False,
        ).exclude(
            telegram_chat_id="",
        ).exists()

        return DashboardData(
            monitoring_targets_count=targets_queryset.count(),
            active_targets_count=targets_queryset.filter(
                is_active=True,
            ).count(),
            inactive_targets_count=targets_queryset.filter(
                is_active=False,
            ).count(),
            targets_with_errors_count=targets_queryset.exclude(
                Q(last_error__isnull=True) | Q(last_error=""),
            ).count(),

            alerts_count=alerts_queryset.count(),
            new_alerts_count=alerts_queryset.filter(
                status="new",
            ).count(),

            notification_channels_count=channels_queryset.count(),
            active_notification_channels_count=channels_queryset.filter(
                is_active=True,
            ).count(),
            telegram_connected=telegram_connected,

            notification_deliveries_count=deliveries_queryset.count(),
            sent_notification_deliveries_count=deliveries_queryset.filter(
                status=NotificationDelivery.Status.SENT,
            ).count(),
            failed_notification_deliveries_count=deliveries_queryset.filter(
                status=NotificationDelivery.Status.FAILED,
            ).count(),

            last_alert_created_at=last_alert.created_at if last_alert else None,
            last_notification_delivery_created_at=(
                last_delivery.created_at if last_delivery else None
            ),
        )
