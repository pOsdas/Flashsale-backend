from django.db import models

from app.api.v1.orders.models import Order


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    class Provider(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        MOCK = "mock", "Mock"

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
    )
    provider = models.CharField(
        max_length=64,
        choices=Provider.choices,
        default=Provider.MOCK,
    )
    provider_payment_id = models.CharField(
        max_length=128,
        unique=True,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.CREATED,
    )
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=8, default="EUR")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["provider", "provider_payment_id"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["order", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"Payment(id={self.id}, order={self.order_id}, "
            f"provider={self.provider}, status={self.status})"
        )


class ProcessedWebhookEvent(models.Model):
    provider = models.CharField(max_length=64)
    event_id = models.CharField(max_length=128)
    received_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()

    class Meta:
        unique_together = [("provider", "event_id")]
        indexes = [models.Index(fields=["provider", "received_at"])]

    def __str__(self) -> str:
        return f"WebhookEvent(provider={self.provider}, event_id={self.event_id})"
