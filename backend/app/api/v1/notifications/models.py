from django.conf import settings
from django.db import models


class NotificationChannel(models.Model):
    class ChannelType(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "Email"
        WEBHOOK = "webhook", "Webhook"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_channels",
        verbose_name="Пользователь",
    )

    type = models.CharField(
        max_length=32,
        choices=ChannelType.choices,
        verbose_name="Тип канала",
    )

    telegram_chat_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Telegram chat ID",
    )

    email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email",
    )

    webhook_url = models.URLField(
        blank=True,
        default="",
        verbose_name="Webhook URL",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        db_table = "notification_channels"
        verbose_name = "Канал уведомлений"
        verbose_name_plural = "Каналы уведомлений"
        indexes = [
            models.Index(fields=["user", "type"]),
            models.Index(fields=["type", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "telegram_chat_id"],
                name="unique_user_telegram_channel",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} | {self.type} | active={self.is_active}"


class NotificationDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
        verbose_name="Пользователь",
    )

    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries",
        verbose_name="Канал уведомления",
    )

    alert = models.ForeignKey(
        "monitoring.Alert",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_deliveries",
        verbose_name="Alert",
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="Статус",
    )

    message_text = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст сообщения",
    )

    error = models.TextField(
        blank=True,
        default="",
        verbose_name="Ошибка",
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отправки",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        db_table = "notification_deliveries"
        verbose_name = "Доставка уведомления"
        verbose_name_plural = "Доставки уведомлений"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["alert", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}, {self.status}, alert={self.alert_id}"