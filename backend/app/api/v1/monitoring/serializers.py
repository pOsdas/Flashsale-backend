from rest_framework import serializers

from app.api.v1.monitoring.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    MonitoringTargetStatus,
    ProductSnapshot,
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
        allowed_values = {choice[0] for choice in Marketplace.choices}

        if value not in allowed_values:
            raise serializers.ValidationError(
                f"Unsupported marketplace. Allowed values: {', '.join(sorted(allowed_values))}."
            )

        return value

    def validate_role(self, value: str) -> str:
        allowed_values = {choice[0] for choice in MonitoringTargetRole.choices}

        if value not in allowed_values:
            raise serializers.ValidationError(
                f"Unsupported target role. Allowed values: {', '.join(sorted(allowed_values))}."
            )

        return value

    def validate_check_interval_minutes(self, value: int) -> int:
        if value < 15:
            raise serializers.ValidationError(
                "Check interval must be at least 15 minutes."
            )

        if value > 24 * 60:
            raise serializers.ValidationError(
                "Check interval must be less than or equal to 1440 minutes."
            )

        return value

    def validate(self, attrs):
        url = attrs.get("url", "")
        marketplace = attrs.get("marketplace")

        if marketplace == Marketplace.WILDBERRIES and "wildberries" not in url.lower():
            raise serializers.ValidationError(
                {
                    "url": "Wildberries target URL must contain wildberries domain."
                }
            )

        if marketplace == Marketplace.OZON and "ozon" not in url.lower():
            raise serializers.ValidationError(
                {
                    "url": "Ozon target URL must contain ozon domain."
                }
            )

        return attrs

    def get_latest_price(self, obj: MonitoringTarget):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None or snapshot.price is None:
            return None

        return str(snapshot.price)

    def get_latest_rating(self, obj: MonitoringTarget):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None or snapshot.rating is None:
            return None

        return str(snapshot.rating)

    def get_latest_reviews_count(self, obj: MonitoringTarget):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.reviews_count

    def get_latest_is_available(self, obj: MonitoringTarget):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.is_available

    def get_latest_checked_at(self, obj: MonitoringTarget):
        snapshot = self._get_latest_snapshot(obj)

        if snapshot is None:
            return None

        return snapshot.checked_at

    def _get_latest_snapshot(self, obj: MonitoringTarget) -> ProductSnapshot | None:
        return obj.snapshots.order_by("-checked_at").first()


class ProductSnapshotSerializer(serializers.ModelSerializer):
    target_id = serializers.UUIDField(source="target.id", read_only=True)

    class Meta:
        model = ProductSnapshot
        fields = (
            "id",
            "target_id",
            "parse_status",
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


class AlertSerializer(serializers.ModelSerializer):
    target_id = serializers.UUIDField(source="target.id", read_only=True)
    snapshot_id = serializers.UUIDField(source="snapshot.id", read_only=True)
    target_title = serializers.CharField(source="target.title", read_only=True)
    target_url = serializers.CharField(source="target.url", read_only=True)
    marketplace = serializers.CharField(source="target.marketplace", read_only=True)

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
        choices=[
            ("wb", "Wildberries"),
            ("ozon", "Ozon"),
        ],
    )
    url = serializers.URLField(
        max_length=2000,
    )


class ProductPreviewResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    product = serializers.DictField()


class ProductPreviewErrorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    error = serializers.CharField()

