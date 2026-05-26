from prometheus_client import Counter, Gauge, Histogram

OUTBOX_EVENTS_PROCESSED_TOTAL = Counter(
    "outbox_events_processed_total",
    "Total number of successfully outbox events",
    ["topic"],
)

OUTBOX_EVENTS_FAILED_TOTAL = Counter(
    "outbox_events_failed_total",
    "Total number of failed outbox event processing attempts",
    ["topic"],
)

OUTBOX_EVENT_PROCESSING_DURATION_SECONDS = Histogram(
    "outbox_event_processing_duration_seconds",
    "Outbox event processing duration in seconds",
    ["topic"],
)

OUTBOX_PENDING_EVENTS = Gauge(
    "outbox_pending_events",
    "Current number of pending outbox events",
)

OUTBOX_FAILED_EVENTS = Gauge(
    "outbox_failed_events",
    "Current number of failed outbox events",
)

OUTBOX_PROCESSING_EVENTS = Gauge(
    "outbox_processing_events",
    "Current number of processing outbox events",
)
