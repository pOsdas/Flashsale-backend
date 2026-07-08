import logging

from django.db.models import Count, Min
from django.utils import timezone
from prometheus_client import Counter, Gauge, Histogram


logger = logging.getLogger(__name__)


NOTIFICATION_MESSAGES_TOTAL = Counter(
    "notification_rabbitmq_messages_total",
    "Total number of RabbitMQ messages consumed by notification consumer",
    ["topic", "status"],
)

NOTIFICATION_MESSAGE_PROCESSING_DURATION_SECONDS = Histogram(
    "notification_rabbitmq_message_processing_duration_seconds",
    "Notification RabbitMQ message processing duration in seconds",
    ["topic"],
)

NOTIFICATION_CONSUMER_RUNNING = Gauge(
    "notification_consumer_running",
    "Whether the notification consumer is running and consuming messages",
)

NOTIFICATION_CONSUMER_HEARTBEAT_TIMESTAMP_SECONDS = Gauge(
    "notification_consumer_heartbeat_timestamp_seconds",
    "Unix timestamp of the latest notification consumer heartbeat",
)

NOTIFICATION_CONSUMER_MESSAGES_IN_PROGRESS = Gauge(
    "notification_consumer_messages_in_progress",
    "Current number of RabbitMQ messages being processed",
)

NOTIFICATION_CONSUMER_LAST_PROCESSED_TIMESTAMP_SECONDS = Gauge(
    "notification_consumer_last_processed_timestamp_seconds",
    "Unix timestamp of the last successfully processed RabbitMQ message",
)

NOTIFICATION_CONSUMER_LAST_FAILED_TIMESTAMP_SECONDS = Gauge(
    "notification_consumer_last_failed_timestamp_seconds",
    "Unix timestamp of the last failed RabbitMQ message",
)

NOTIFICATION_DELIVERIES_TOTAL = Counter(
    "notification_deliveries_total",
    "Total number of notification delivery attempts",
    ["channel", "status"],
)

NOTIFICATION_DELIVERY_RECORDS = Gauge(
    "notification_delivery_records",
    "Current number of notification delivery records by status",
    ["status"],
)

NOTIFICATION_OLDEST_PENDING_DELIVERY_AGE_SECONDS = Gauge(
    "notification_oldest_pending_delivery_age_seconds",
    "Age in seconds of the oldest pending notification delivery",
)

NOTIFICATION_DELIVERY_METRICS_REFRESH_ERRORS_TOTAL = Counter(
    "notification_delivery_metrics_refresh_errors_total",
    "Total number of notification delivery state metrics refresh errors",
)

TELEGRAM_NOTIFICATIONS_TOTAL = Counter(
    "telegram_notifications_total",
    "Total number of Telegram notification delivery attempts",
    ["status"],
)

TELEGRAM_NOTIFICATION_DURATION_SECONDS = Histogram(
    "telegram_notification_duration_seconds",
    "Telegram notification delivery duration in seconds",
)


def refresh_notification_delivery_state_metrics() -> None:
    """
    sync Prometheus Gauge with current DB state.
    """
    from app.api.v1.notifications.models import NotificationDelivery

    try:
        status_counts = dict(
            NotificationDelivery.objects
            .values("status")
            .annotate(total=Count("id"))
            .values_list("status", "total")
        )

        for status in NotificationDelivery.Status.values:
            NOTIFICATION_DELIVERY_RECORDS.labels(
                status=status,
            ).set(
                status_counts.get(status, 0)
            )

        oldest_pending_at = (
            NotificationDelivery.objects
            .filter(
                status=NotificationDelivery.Status.PENDING,
            )
            .aggregate(
                oldest=Min("created_at"),
            )
            .get("oldest")
        )

        if oldest_pending_at is None:
            NOTIFICATION_OLDEST_PENDING_DELIVERY_AGE_SECONDS.set(0)
            return

        oldest_pending_age_seconds = max(
            0.0,
            (
                timezone.now() - oldest_pending_at
            ).total_seconds(),
        )

        NOTIFICATION_OLDEST_PENDING_DELIVERY_AGE_SECONDS.set(
            oldest_pending_age_seconds
        )

    except Exception:
        NOTIFICATION_DELIVERY_METRICS_REFRESH_ERRORS_TOTAL.inc()

        logger.exception(
            "Failed to refresh notification delivery metrics",
            extra={
                "service": "notification_consumer",
            },
        )