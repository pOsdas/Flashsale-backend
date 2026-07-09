from prometheus_client import Counter, Gauge, Histogram


TELEGRAM_BOT_RUNNING = Gauge(
    "telegram_bot_running",
    "Whether the Telegram polling bot is running",
)

TELEGRAM_POLLING_HEARTBEAT_TIMESTAMP_SECONDS = Gauge(
    "telegram_polling_heartbeat_timestamp_seconds",
    "Unix timestamp of the latest successful Telegram getUpdates request",
)

TELEGRAM_LAST_UPDATE_TIMESTAMP_SECONDS = Gauge(
    "telegram_last_update_timestamp_seconds",
    "Unix timestamp of the latest handled Telegram update",
)

TELEGRAM_POLLING_REQUESTS_TOTAL = Counter(
    "telegram_polling_requests_total",
    "Total number of Telegram getUpdates requests",
    ["status"],
)

TELEGRAM_POLLING_REQUEST_DURATION_SECONDS = Histogram(
    "telegram_polling_request_duration_seconds",
    "Telegram getUpdates request duration in seconds",
)

TELEGRAM_UPDATES_TOTAL = Counter(
    "telegram_updates_total",
    "Total number of received Telegram updates",
    ["update_type", "status"],
)

TELEGRAM_UPDATES_IN_PROGRESS = Gauge(
    "telegram_updates_in_progress",
    "Current number of Telegram updates being processed",
)

TELEGRAM_HANDLER_ERRORS_TOTAL = Counter(
    "telegram_handler_errors_total",
    "Total number of Telegram bot handler errors",
    ["stage"],
)

TELEGRAM_COMMANDS_TOTAL = Counter(
    "telegram_commands_total",
    "Total number of Telegram bot commands",
    ["command"],
)

TELEGRAM_CALLBACKS_TOTAL = Counter(
    "telegram_callbacks_total",
    "Total number of Telegram callback queries",
    ["handler"],
)

TELEGRAM_PREVIEWS_TOTAL = Counter(
    "telegram_product_previews_total",
    "Total number of Telegram product preview attempts",
    ["marketplace", "result"],
)

TELEGRAM_TARGET_CREATIONS_TOTAL = Counter(
    "telegram_target_creations_total",
    "Total number of monitoring target creation actions from Telegram",
    ["marketplace", "result"],
)

TELEGRAM_TARGET_ACTIONS_TOTAL = Counter(
    "telegram_target_actions_total",
    "Total number of monitoring target actions from Telegram",
    ["action", "result"],
)

TELEGRAM_RATE_LIMIT_DECISIONS_TOTAL = Counter(
    "telegram_rate_limit_decisions_total",
    "Total number of Telegram action rate limit decisions",
    ["scope", "result"],
)


def normalize_marketplace_label(value: object) -> str:
    """Return a bounded, stable label value for marketplace enums/strings."""
    raw_value = getattr(value, "value", value)
    normalized = str(raw_value or "unknown").strip().lower()
    return normalized or "unknown"
