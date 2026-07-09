from prometheus_client import Counter, Gauge, Histogram


MONITORING_GO_FETCHER_REQUESTS_TOTAL = Counter(
    "monitoring_go_fetcher_requests_total",
    "Total number of backend requests to go_fetcher",
    [
        "marketplace",
        "result",
        "status_class",
    ],
)

MONITORING_GO_FETCHER_REQUEST_DURATION_SECONDS = Histogram(
    "monitoring_go_fetcher_request_duration_seconds",
    "Backend to go_fetcher request duration in seconds",
    [
        "marketplace",
        "result",
    ],
    buckets=(
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        20.0,
        40.0,
        60.0,
    ),
)

MONITORING_GO_FETCHER_REQUESTS_IN_PROGRESS = Gauge(
    "monitoring_go_fetcher_requests_in_progress",
    "Current number of backend requests to go_fetcher",
    [
        "marketplace",
    ],
)

MONITORING_GO_FETCHER_LAST_SUCCESS_TIMESTAMP_SECONDS = Gauge(
    "monitoring_go_fetcher_last_success_timestamp_seconds",
    "Unix timestamp of the latest successful go_fetcher response",
    [
        "marketplace",
    ],
)
