from prometheus_client import Counter, Gauge, Histogram


MONITORING_PRODUCT_CACHE_LOOKUPS_TOTAL = Counter(
    "monitoring_product_cache_lookups_total",
    "Total number of top-level product cache lookups",
    [
        "marketplace",
        "operation",
        "result",
    ],
)

MONITORING_PRODUCT_CACHE_REQUESTS_TOTAL = Counter(
    "monitoring_product_cache_requests_total",
    "Total number of product cache service requests by final result",
    [
        "marketplace",
        "operation",
        "result",
    ],
)

MONITORING_PRODUCT_CACHE_LOCK_EVENTS_TOTAL = Counter(
    "monitoring_product_cache_lock_events_total",
    "Total number of product cache refresh lock events",
    [
        "marketplace",
        "result",
    ],
)

MONITORING_PRODUCT_CACHE_REFRESHES_TOTAL = Counter(
    "monitoring_product_cache_refreshes_total",
    "Total number of product cache refresh attempts",
    [
        "marketplace",
        "result",
    ],
)

MONITORING_PRODUCT_CACHE_REFRESH_DURATION_SECONDS = Histogram(
    "monitoring_product_cache_refresh_duration_seconds",
    "Product cache refresh duration in seconds",
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

MONITORING_PRODUCT_CACHE_REFRESHES_IN_PROGRESS = Gauge(
    "monitoring_product_cache_refreshes_in_progress",
    "Current number of product cache refreshes in progress",
    [
        "marketplace",
    ],
)

MONITORING_PRODUCT_CACHE_WAIT_DURATION_SECONDS = Histogram(
    "monitoring_product_cache_wait_duration_seconds",
    "Time spent waiting for another product cache refresh",
    [
        "marketplace",
        "result",
    ],
    buckets=(
        0.1,
        0.25,
        0.5,
        1.0,
        2.0,
        3.0,
        5.0,
        10.0,
    ),
)

MONITORING_PRODUCT_CACHE_ENTRY_AGE_SECONDS = Histogram(
    "monitoring_product_cache_entry_age_seconds",
    "Age of product cache entries when they are served",
    [
        "marketplace",
        "source",
    ],
    buckets=(
        1.0,
        5.0,
        15.0,
        30.0,
        60.0,
        300.0,
        900.0,
        1800.0,
        3600.0,
        7200.0,
        21600.0,
        43200.0,
        86400.0,
    ),
)
