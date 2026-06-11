from rest_framework import serializers

from app.api.v1.notifications.models import NotificationChannel, NotificationDelivery


class NotificationChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannel
        fields = [
            "id",
            "type",
            "telegram_chat_id",
            "email",
            "webhook_url",
            "enabled_alert_types",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_enabled_alert_types(self, value):
        if value is None:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(
                "enabled_alert_types должен быть списком."
            )

        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError(
                    "Каждый тип alert должен быть строкой."
                )

            if not item.strip():
                raise serializers.ValidationError(
                    "Тип alert не может быть пустой строкой."
                )

        return [item.strip() for item in value]

    def validate(self, attrs):
        channel_type = attrs.get("type") or getattr(self.instance, "type", None)

        telegram_chat_id = attrs.get("telegram_chat_id")
        email = attrs.get("email")
        webhook_url = attrs.get("webhook_url")

        if self.instance:
            if telegram_chat_id is None:
                telegram_chat_id = self.instance.telegram_chat_id

            if email is None:
                email = self.instance.email

            if webhook_url is None:
                webhook_url = self.instance.webhook_url

        if channel_type == NotificationChannel.ChannelType.TELEGRAM:
            if not telegram_chat_id:
                raise serializers.ValidationError(
                    {
                        "telegram_chat_id": "Для Telegram-канала нужно указать telegram_chat_id."
                    }
                )

        if channel_type == NotificationChannel.ChannelType.EMAIL:
            if not email:
                raise serializers.ValidationError(
                    {"email": "Для Email-канала нужно указать email."}
                )

        if channel_type == NotificationChannel.ChannelType.WEBHOOK:
            if not webhook_url:
                raise serializers.ValidationError(
                    {"webhook_url": "Для Webhook-канала нужно указать webhook_url."}
                )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user

        channel_type = validated_data["type"]

        if channel_type == NotificationChannel.ChannelType.TELEGRAM:
            telegram_chat_id = validated_data.get("telegram_chat_id", "")

            channel, _ = NotificationChannel.objects.update_or_create(
                user=user,
                type=NotificationChannel.ChannelType.TELEGRAM,
                telegram_chat_id=telegram_chat_id,
                defaults={
                    "is_active": validated_data.get("is_active", True),
                    "email": validated_data.get("email", ""),
                    "webhook_url": validated_data.get("webhook_url", ""),
                    "enabled_alert_types": validated_data.get(
                        "enabled_alert_types",
                        [],
                    ),
                },
            )

            return channel

        return NotificationChannel.objects.create(
            user=user,
            **validated_data,
        )


class TelegramConnectLinkSerializer(serializers.Serializer):
    token = serializers.CharField()
    url = serializers.URLField()
    expires_in_seconds = serializers.IntegerField()


class TelegramOnboardingSerializer(serializers.Serializer):
    telegram_chat_id = serializers.CharField(
        max_length=128,
    )

    def validate_telegram_chat_id(self, value: str) -> str:
        value = value.strip()

        if not value:
            raise serializers.ValidationError("telegram_chat_id не может быть пустым.")

        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        telegram_chat_id = self.validated_data["telegram_chat_id"]

        channel, created = NotificationChannel.objects.update_or_create(
            user=user,
            type=NotificationChannel.ChannelType.TELEGRAM,
            telegram_chat_id=telegram_chat_id,
            defaults={
                "is_active": True,
                "email": "",
                "webhook_url": "",
            },
        )

        self.instance = channel
        self.created = created

        return channel


class TelegramOnboardingResponseSerializer(serializers.ModelSerializer):
    message = serializers.SerializerMethodField()

    class Meta:
        model = NotificationChannel
        fields = [
            "id",
            "type",
            "telegram_chat_id",
            "enabled_alert_types",
            "is_active",
            "message",
            "created_at",
            "updated_at",
        ]

    def get_message(self, obj) -> str:
        return "Telegram успешно подключен."


class NotificationDeliveryHistorySerializer(serializers.ModelSerializer):
    channel_id = serializers.IntegerField(source="channel.id", read_only=True)
    channel_type = serializers.CharField(source="channel.type", read_only=True)
    channel_is_active = serializers.BooleanField(
        source="channel.is_active", read_only=True
    )

    alert_id = serializers.SerializerMethodField()
    # alert_type = serializers.SerializerMethodField()
    # target_id = serializers.SerializerMethodField()

    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "status",
            "channel_id",
            "channel_type",
            "channel_is_active",
            "alert_id",
            # "alert_type",
            # "target_id",
            "message_text",
            "error",
            "created_at",
            "updated_at",
            "sent_at",
        ]
        read_only_fields = fields

    def get_alert_id(self, obj):
        if obj.alert_id is None:
            return None

        return str(obj.alert_id)

    # def get_alert_type(self, obj):
    #     alert = getattr(obj, "alert", None)
    #
    #     if alert is None:
    #         return None
    #
    #     return getattr(alert, "type", None)

    # def get_target_id(self, obj):
    #     alert = getattr(obj, "alert", None)
    #
    #     if alert is None:
    #         return None
    #
    #     target = getattr(alert, "target", None)
    #
    #     if target is None:
    #         return None
    #
    #     return getattr(target, "id", None)
