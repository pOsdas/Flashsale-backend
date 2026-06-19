from rest_framework import serializers

from app.api.v1.monitoring.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    ProductSnapshot,
    SnapshotSource,
)
from app.api.v1.monitoring.services.alert_rule_constants import (
    ALERT_RULE_SOURCES,
    MAX_ALERT_RULE_COOLDOWN_MINUTES,
    NUMERIC_ALERT_TYPES,
    SUPPORTED_TARGET_ALERT_TYPES,
)


class MonitoringTargetSerializer(serializers.ModelSerializer):
    latest_price = serializers.SerializerMethodField()
    latest_rating = serializers.SerializerMethodField()
    latest_reviews_count = serializers.SerializerMethodField()
    latest_is_available = serializers.SerializerMethodField()
    latest_checked_at = serializers.SerializerMethodField()

    class Meta:
        model = MonitoringTarget
        fields = (
            "id",
            "marketplace",
            "role",
            "status",
            "url",
            "external_id",
            "title",
            "seller_name",
            "brand",
            "check_interval_minutes",
            "last_checked_at",
            "next_check_at",
            "last_error",
            "is_active",
            "latest_price",
            "latest_rating",
            "latest_reviews_count",
            "latest_is_available",
            "latest_checked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "external_id",
            "title",
            "seller_name",
            "brand",
            "last_checked_at",
            "next_check_at",
            "last_error",
            "is_active",
            "latest_price",
            "latest_rating",
            "latest_reviews_count",
            "latest_is_available",
            "latest_checked_at",
            "created_at",
            "updated_at",
        )

    def validate_marketplace(self, value: str) -> str:
        allowed_values = {
            choice[0]
            for choice in Marketplace.choices
        }

        if value not in allowed_values:
            raise serializers.ValidationError(
                "Unsupported marketplace. "
                f"Allowed values: {', '.join(sorted(allowed_values))}."
            )

        return value

    def validate_role(self, value: str) -> str:
        allowed_values = {
            choice[0]
            for choice in MonitoringTargetRole.choices
        }

        if value not in allowed_values:
            raise serializers.ValidationError(
                "Unsupported target role. "
                f"Allowed values: {', '.join(sorted(allowed_values))}."
            )

        return value

    def validate_check_interval_minutes(
        self,
        value: int,
    ) -> int:
        if value < 15:
            raise serializers.ValidationError(
                "Check interval must be at least 15 minutes."
            )

        if value > 1440:
            raise serializers.ValidationError(
                "Check interval must be less than or equal "
                "to 1440 minutes."
            )

        return value

    def validate(self, attrs):
        url = attrs.get("url", "")
        marketplace = attrs.get("marketplace")

        if (
            marketplace == Marketplace.WILDBERRIES
            and "wildberries" not in url.lower()
        ):
            raise serializers.ValidationError(
                {
                    "url": (
                        "Wildberries target URL must contain "
                        "wildberries domain."
                    )
                }
            )

        if (
            marketplace == Marketplace.OZON
            and "ozon" not in url.lower()
        ):
            raise serializers.ValidationError(
                {
                    "url": (
                        "Ozon target URL must contain ozon domain."
                    )
                }
            )

        return attrs

    def get_latest_price(
        self,
        obj: MonitoringTarget,
    ):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None or snapshot.price is None:
            return None

        return str(snapshot.price)

    def get_latest_rating(
        self,
        obj: MonitoringTarget,
    ):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None or snapshot.rating is None:
            return None

        return str(snapshot.rating)

    def get_latest_reviews_count(
        self,
        obj: MonitoringTarget,
    ):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.reviews_count

    def get_latest_is_available(
        self,
        obj: MonitoringTarget,
    ):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.is_available

    def get_latest_checked_at(
        self,
        obj: MonitoringTarget,
    ):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.checked_at

    def _get_latest_snapshot(
        self,
        obj: MonitoringTarget,
    ) -> ProductSnapshot | None:
        prefetched_snapshots = (
            getattr(
                obj,
                "_prefetched_objects_cache",
                {},
            )
            .get("snapshots")
        )

        if prefetched_snapshots is not None:
            if not prefetched_snapshots:
                return None

            return prefetched_snapshots[0]

        return (
            obj.snapshots
            .order_by("-checked_at")
            .first()
        )


class MonitoringTargetUpdateSerializer(
    serializers.Serializer,
):
    role = serializers.ChoiceField(
        choices=MonitoringTargetRole.choices,
        required=False,
    )
    check_interval_minutes = serializers.IntegerField(
        min_value=15,
        max_value=1440,
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "At least one field must be provided."
            )

        return attrs


class ProductSnapshotSerializer(serializers.ModelSerializer):
    target_id = serializers.UUIDField(
        source="target.id",
        read_only=True,
    )

    class Meta:
        model = ProductSnapshot
        fields = (
            "id",
            "target_id",
            "parse_status",
            "source",
            "price",
            "old_price",
            "currency",
            "is_available",
            "rating",
            "reviews_count",
            "title",
            "seller_name",
            "brand",
            "raw_data",
            "error_message",
            "checked_at",
            "created_at",
        )
        read_only_fields = fields


class MonitoringTargetCheckNowResponseSerializer(
    serializers.Serializer,
):
    success = serializers.BooleanField()
    target = MonitoringTargetSerializer()
    snapshot = ProductSnapshotSerializer()
    alerts_count = serializers.IntegerField(
        min_value=0,
    )
    cache_source = serializers.ChoiceField(
        choices=SnapshotSource.choices,
    )
    cache_is_stale = serializers.BooleanField()
    effective_cache_minutes = serializers.IntegerField(
        min_value=1,
    )


class MonitoringTargetActionErrorSerializer(
    serializers.Serializer,
):
    success = serializers.BooleanField()
    error_code = serializers.CharField()
    error = serializers.CharField()


class AlertRuleSettingWriteSerializer(
    serializers.Serializer,
):
    alert_type = serializers.ChoiceField(
        choices=SUPPORTED_TARGET_ALERT_TYPES,
    )
    threshold_percent = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
    )
    threshold_absolute = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
    )
    cooldown_minutes = serializers.IntegerField(
        min_value=0,
        max_value=MAX_ALERT_RULE_COOLDOWN_MINUTES,
    )
    is_enabled = serializers.BooleanField()

    def validate(self, attrs):
        alert_type = attrs["alert_type"]

        if alert_type not in NUMERIC_ALERT_TYPES:
            if (
                attrs["threshold_percent"] is not None
                or attrs["threshold_absolute"] is not None
            ):
                raise serializers.ValidationError(
                    "Thresholds are not supported for "
                    f"alert type {alert_type}."
                )

        return attrs


class MonitoringTargetAlertSettingsUpdateSerializer(
    serializers.Serializer,
):
    rules = AlertRuleSettingWriteSerializer(
        many=True,
        allow_empty=False,
    )

    def validate_rules(self, rules):
        received_types = [
            rule["alert_type"]
            for rule in rules
        ]

        duplicate_types = {
            alert_type
            for alert_type in received_types
            if received_types.count(alert_type) > 1
        }

        if duplicate_types:
            raise serializers.ValidationError(
                "Duplicate alert rule types: "
                f"{', '.join(sorted(duplicate_types))}."
            )

        received_type_set = set(received_types)
        supported_type_set = set(
            SUPPORTED_TARGET_ALERT_TYPES
        )

        missing_types = (
            supported_type_set - received_type_set
        )
        unsupported_types = (
            received_type_set - supported_type_set
        )

        if missing_types:
            raise serializers.ValidationError(
                "Missing alert rule types: "
                f"{', '.join(sorted(missing_types))}."
            )

        if unsupported_types:
            raise serializers.ValidationError(
                "Unsupported alert rule types: "
                f"{', '.join(sorted(unsupported_types))}."
            )

        return rules


class AlertRuleSettingResponseSerializer(
    serializers.Serializer,
):
    alert_type = serializers.ChoiceField(
        choices=SUPPORTED_TARGET_ALERT_TYPES,
    )
    threshold_percent = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        allow_null=True,
    )
    threshold_absolute = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
    )
    cooldown_minutes = serializers.IntegerField()
    is_enabled = serializers.BooleanField()
    is_custom = serializers.BooleanField()
    source = serializers.ChoiceField(
        choices=ALERT_RULE_SOURCES,
    )


class MonitoringTargetAlertSettingsResponseSerializer(
    serializers.Serializer,
):
    target_id = serializers.UUIDField()
    rules = AlertRuleSettingResponseSerializer(
        many=True,
    )


class AlertSerializer(serializers.ModelSerializer):
    target_id = serializers.UUIDField(
        source="target.id",
        read_only=True,
    )
    snapshot_id = serializers.UUIDField(
        source="snapshot.id",
        read_only=True,
    )
    target_title = serializers.CharField(
        source="target.title",
        read_only=True,
    )
    target_url = serializers.CharField(
        source="target.url",
        read_only=True,
    )
    marketplace = serializers.CharField(
        source="target.marketplace",
        read_only=True,
    )

    class Meta:
        model = Alert
        fields = (
            "id",
            "target_id",
            "snapshot_id",
            "target_title",
            "target_url",
            "marketplace",
            "alert_type",
            "severity",
            "status",
            "title",
            "message",
            "old_value",
            "new_value",
            "dedup_key",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AlertQuerySerializer(serializers.Serializer):
    target_id = serializers.UUIDField(
        required=False,
    )
    alert_type = serializers.ChoiceField(
        choices=AlertType.choices,
        required=False,
    )
    severity = serializers.ChoiceField(
        choices=AlertSeverity.choices,
        required=False,
    )
    status = serializers.ChoiceField(
        choices=AlertStatus.choices,
        required=False,
    )


class ProductPreviewRequestSerializer(serializers.Serializer):
    marketplace = serializers.ChoiceField(
        choices=Marketplace.choices,
    )
    url = serializers.URLField(
        max_length=2000,
    )


class ProductPreviewResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    product = serializers.DictField()


class ProductPreviewErrorResponseSerializer(
    serializers.Serializer,
):
    success = serializers.BooleanField()
    error = serializers.CharField()
