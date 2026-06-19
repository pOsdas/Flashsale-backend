import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Marketplace(models.TextChoices):
    WILDBERRIES = "wb", "Wildberries"
    OZON = "ozon", "Ozon"


class MonitoringTargetRole(models.TextChoices):
    OWN = "own", "Own product"
    COMPETITOR = "competitor", "Competitor product"


class MonitoringTargetStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    FAILED = "failed", "Failed"


class SnapshotParseStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    NOT_FOUND = "not_found", "Not found"
    BLOCKED = "blocked", "Blocked"
    PARSE_ERROR = "parse_error", "Parse error"
    MARKETPLACE_ERROR = "marketplace_error", "Marketplace error"


class SnapshotSource(models.TextChoices):
    PARSER = "parser", "Parser"
    CACHE = "cache", "Cache"
    STALE_CACHE = "stale_cache", "Stale cache"


class AlertType(models.TextChoices):
    PRICE_CHANGED = "price_changed", "Price changed"
    PRICE_DROPPED = "price_dropped", "Price dropped"
    PRICE_INCREASED = "price_increased", "Price increased"
    AVAILABILITY_CHANGED = (
        "availability_changed",
        "Availability changed",
    )
    BECAME_AVAILABLE = "became_available", "Became available"
    BECAME_UNAVAILABLE = (
        "became_unavailable",
        "Became unavailable",
    )
    RATING_CHANGED = "rating_changed", "Rating changed"
    REVIEWS_COUNT_CHANGED = (
        "reviews_count_changed",
        "Reviews count changed",
    )
    TITLE_CHANGED = "title_changed", "Title changed"


class AlertSeverity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class AlertStatus(models.TextChoices):
    NEW = "new", "New"
    SENT = "sent", "Sent"
    SKIPPED = "skipped", "Skipped"
    FAILED = "failed", "Failed"


class MonitoringTarget(models.Model):
    """
    Product or marketplace page that should be monitored.

    MVP usage:
    - one row = one tracked WB/Ozon product
    - target can be user's own product or competitor product
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="monitoring_targets",
    )

    marketplace = models.CharField(
        max_length=20,
        choices=Marketplace.choices,
    )
    role = models.CharField(
        max_length=20,
        choices=MonitoringTargetRole.choices,
        default=MonitoringTargetRole.COMPETITOR,
    )
    status = models.CharField(
        max_length=20,
        choices=MonitoringTargetStatus.choices,
        default=MonitoringTargetStatus.ACTIVE,
    )

    url = models.URLField(
        max_length=2000,
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    title = models.CharField(
        max_length=500,
        blank=True,
    )
    seller_name = models.CharField(
        max_length=255,
        blank=True,
    )
    brand = models.CharField(
        max_length=255,
        blank=True,
    )

    check_interval_minutes = models.PositiveIntegerField(
        default=60,
    )
    last_checked_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    next_check_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    last_error = models.TextField(
        blank=True,
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "marketplace"]),
            models.Index(fields=["marketplace", "external_id"]),
            models.Index(fields=["is_active", "next_check_at"]),
            models.Index(fields=["status", "next_check_at"]),
        ]

    def __str__(self) -> str:
        title = self.title or self.external_id or self.url
        return f"{self.marketplace}: {title}"


class ProductCacheEntry(models.Model):
    """
    Shared current product cache.

    One row represents one marketplace product by canonical identity:
    marketplace + external_id.
    MonitoringTarget rows only define how often different users need
    this product.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    marketplace = models.CharField(
        max_length=20,
        choices=Marketplace.choices,
    )
    external_id = models.CharField(
        max_length=255,
        db_index=True,
    )

    url = models.URLField(
        max_length=2000,
        blank=True,
    )
    title = models.CharField(
        max_length=500,
        blank=True,
    )
    seller_name = models.CharField(
        max_length=255,
        blank=True,
    )
    brand = models.CharField(
        max_length=255,
        blank=True,
    )

    data = models.JSONField(
        default=dict,
        blank=True,
    )

    parsed_at = models.DateTimeField(
        db_index=True,
    )
    expires_at = models.DateTimeField(
        db_index=True,
    )
    effective_cache_minutes = models.PositiveIntegerField(
        default=60,
    )

    last_success_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    last_error = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["marketplace", "external_id"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["parsed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["marketplace", "external_id"],
                name="unique_monitoring_product_cache_entry",
            ),
        ]

    def __str__(self) -> str:
        title = self.title or self.external_id
        return f"{self.marketplace}: {title}"


class ProductSnapshot(models.Model):
    """
    Historical product state.

    Every successful or failed check creates a snapshot.
    This gives us history and allows change detection.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    target = models.ForeignKey(
        MonitoringTarget,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    parse_status = models.CharField(
        max_length=30,
        choices=SnapshotParseStatus.choices,
        default=SnapshotParseStatus.SUCCESS,
        db_index=True,
    )
    source = models.CharField(
        max_length=32,
        choices=SnapshotSource.choices,
        default=SnapshotSource.PARSER,
        db_index=True,
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(
        max_length=10,
        default="RUB",
    )

    is_available = models.BooleanField(
        null=True,
        blank=True,
    )
    rating = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reviews_count = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    title = models.CharField(
        max_length=500,
        blank=True,
    )
    seller_name = models.CharField(
        max_length=255,
        blank=True,
    )
    brand = models.CharField(
        max_length=255,
        blank=True,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )
    error_message = models.TextField(
        blank=True,
    )

    checked_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["target", "-checked_at"]),
            models.Index(fields=["parse_status", "checked_at"]),
            models.Index(fields=["source", "-checked_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.target_id} snapshot at {self.checked_at}"


class AlertRule(models.Model):
    """
    User-configurable alert rule.

    A target-specific rule controls whether an Alert should be created
    for one exact alert type of one MonitoringTarget.

    If a target-specific rule does not exist, application-level default
    settings are used by AlertRuleService.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    target = models.ForeignKey(
        MonitoringTarget,
        on_delete=models.CASCADE,
        related_name="alert_rules",
        null=True,
        blank=True,
    )

    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
    )

    threshold_percent = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Minimum percent change required to trigger this rule."
        ),
    )
    threshold_absolute = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Minimum absolute value change required to trigger "
            "this rule."
        ),
    )

    cooldown_minutes = models.PositiveIntegerField(
        default=360,
        help_text=(
            "Do not create the same alert type for this target "
            "too often."
        ),
    )
    is_enabled = models.BooleanField(
        default=True,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["alert_type"]
        indexes = [
            models.Index(fields=["user", "alert_type"]),
            models.Index(fields=["target", "alert_type"]),
            models.Index(fields=["is_enabled"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["target", "alert_type"],
                condition=models.Q(
                    target__isnull=False,
                ),
                name="unique_monitoring_target_alert_rule",
            ),
            models.UniqueConstraint(
                fields=["user", "alert_type"],
                condition=models.Q(
                    target__isnull=True,
                ),
                name="unique_monitoring_global_alert_rule",
            ),
        ]

    def __str__(self) -> str:
        if self.target_id:
            return (
                f"{self.user_id}:"
                f"{self.target_id}:"
                f"{self.alert_type}"
            )

        return f"{self.user_id}:global:{self.alert_type}"


class Alert(models.Model):
    """
    A detected important change.

    Alert is stored before sending Telegram/email.
    This gives us history, deduplication and debugging.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    target = models.ForeignKey(
        MonitoringTarget,
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    snapshot = models.ForeignKey(
        ProductSnapshot,
        on_delete=models.CASCADE,
        related_name="alerts",
    )

    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=20,
        choices=AlertSeverity.choices,
        default=AlertSeverity.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.NEW,
        db_index=True,
    )

    title = models.CharField(
        max_length=255,
    )
    message = models.TextField()

    old_value = models.JSONField(
        null=True,
        blank=True,
    )
    new_value = models.JSONField(
        null=True,
        blank=True,
    )

    dedup_key = models.CharField(
        max_length=500,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["target", "-created_at"]),
            models.Index(fields=["alert_type", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedup_key"],
                name="unique_monitoring_alert_dedup_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.alert_type}: {self.title}"
