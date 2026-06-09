from django.contrib import admin

from app.api.v1.notifications.models import NotificationChannel, NotificationDelivery


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "type",
        "telegram_chat_id",
        "email",
        "webhook_url",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "type",
        "is_active",
        "created_at",
    )
    search_fields = (
        "user__id",
        "user__username",
        "user__email",
        "telegram_chat_id",
        "email",
        "webhook_url",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "channel",
        "alert",
        "status",
        "sent_at",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "created_at",
        "sent_at",
    )
    search_fields = (
        "user__id",
        "user__username",
        "user__email",
        "message_text",
        "error",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "sent_at",
    )