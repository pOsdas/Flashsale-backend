from prometheus_client import Counter, Histogram


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

NOTIFICATION_DELIVERIES_TOTAL = Counter(
    "notification_deliveries_total",
    "Total number of notification delivery attempts",
    ["channel", "status"],
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
