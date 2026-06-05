from django.contrib import admin

from app.api.v1.monitoring.models import (
    Alert,
    AlertRule,
    MonitoringTarget,
    ProductSnapshot,
)


@admin.register(MonitoringTarget)
class MonitoringTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "marketplace",
        "role",
        "status",
        "title",
        "external_id",
        "is_active",
        "last_checked_at",
        "next_check_at",
        "created_at",
    )
    list_filter = (
        "marketplace",
        "role",
        "status",
        "is_active",
        "created_at",
    )
    search_fields = (
        "id",
        "url",
        "external_id",
        "title",
        "seller_name",
        "brand",
        "user__email",
        "user__username",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "last_checked_at",
    )
    ordering = ("-created_at",)


@admin.register(ProductSnapshot)
class ProductSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "target",
        "parse_status",
        "price",
        "old_price",
        "is_available",
        "rating",
        "reviews_count",
        "checked_at",
    )
    list_filter = (
        "parse_status",
        "is_available",
        "checked_at",
    )
    search_fields = (
        "id",
        "target__id",
        "target__url",
        "target__external_id",
        "title",
        "seller_name",
        "brand",
    )
    readonly_fields = (
        "id",
        "created_at",
    )
    ordering = ("-checked_at",)


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "target",
        "alert_type",
        "threshold_percent",
        "threshold_absolute",
        "cooldown_minutes",
        "is_enabled",
        "created_at",
    )
    list_filter = (
        "alert_type",
        "is_enabled",
        "created_at",
    )
    search_fields = (
        "id",
        "user__email",
        "user__username",
        "target__url",
        "target__external_id",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )
    ordering = ("alert_type",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "target",
        "alert_type",
        "severity",
        "status",
        "title",
        "created_at",
    )
    list_filter = (
        "alert_type",
        "severity",
        "status",
        "created_at",
    )
    search_fields = (
        "id",
        "title",
        "message",
        "dedup_key",
        "user__email",
        "user__username",
        "target__url",
        "target__external_id",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
