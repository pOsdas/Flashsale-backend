from prometheus_client import Counter, Gauge, Histogram


MONITORING_SCANNER_ITERATIONS_TOTAL = Counter(
    "monitoring_scanner_iterations_total",
    "Total number of monitoring scanner iterations",
    ["status"],
)

MONITORING_SCANNER_ITERATION_DURATION_SECONDS = Histogram(
    "monitoring_scanner_iteration_duration_seconds",
    "Monitoring scanner iteration duration in seconds",
)

MONITORING_SCANNER_LAST_SUCCESS_TIMESTAMP_SECONDS = Gauge(
    "monitoring_scanner_last_success_timestamp_seconds",
    "Unix timestamp of the last successfully completed scanner iteration",
)

MONITORING_SCANNER_LAST_PROCESSED_TARGETS = Gauge(
    "monitoring_scanner_last_processed_targets",
    "Number of targets processed during the last scanner iteration",
)

MONITORING_SCANNER_DUE_TARGETS = Gauge(
    "monitoring_scanner_due_targets",
    "Current number of active monitoring targets due for checking",
)

MONITORING_SCANNER_OVERDUE_TARGETS = Gauge(
    "monitoring_scanner_overdue_targets",
    "Current number of monitoring targets overdue beyond the configured threshold",
)

MONITORING_SCANNER_OLDEST_OVERDUE_AGE_SECONDS = Gauge(
    "monitoring_scanner_oldest_overdue_age_seconds",
    "Age in seconds of the oldest overdue monitoring target",
)

MONITORING_TARGET_PROCESSING_TOTAL = Counter(
    "monitoring_target_processing_total",
    "Total number of monitoring target processing attempts",
    [
        "marketplace",
        "trigger",
        "result",
    ],
)

MONITORING_TARGET_PROCESSING_DURATION_SECONDS = Histogram(
    "monitoring_target_processing_duration_seconds",
    "Monitoring target processing duration in seconds",
    [
        "marketplace",
        "trigger",
    ],
)

MONITORING_SNAPSHOTS_CREATED_TOTAL = Counter(
    "monitoring_snapshots_created_total",
    "Total number of product snapshots created",
    [
        "marketplace",
        "parse_status",
        "trigger",
    ],
)

MONITORING_ALERTS_CREATED_TOTAL = Counter(
    "monitoring_alerts_created_total",
    "Total number of monitoring alerts created",
    [
        "marketplace",
        "trigger",
    ],
)

MONITORING_CACHE_RESULTS_TOTAL = Counter(
    "monitoring_cache_results_total",
    "Total number of monitoring product cache results",
    [
        "marketplace",
        "source",
        "is_stale",
        "trigger",
    ],
)
