from rest_framework import serializers


class DashboardSerializer(serializers.Serializer):
    monitoring_targets_count = serializers.IntegerField()
    active_targets_count = serializers.IntegerField()
    inactive_targets_count = serializers.IntegerField()
    targets_with_errors_count = serializers.IntegerField()

    alerts_count = serializers.IntegerField()
    new_alerts_count = serializers.IntegerField()

    notification_channels_count = serializers.IntegerField()
    active_notification_channels_count = serializers.IntegerField()
    telegram_connected = serializers.BooleanField()

    notification_deliveries_count = serializers.IntegerField()
    sent_notification_deliveries_count = serializers.IntegerField()
    failed_notification_deliveries_count = serializers.IntegerField()

    last_alert_created_at = serializers.DateTimeField(
        allow_null=True,
    )
    last_notification_delivery_created_at = serializers.DateTimeField(
        allow_null=True,
    )
