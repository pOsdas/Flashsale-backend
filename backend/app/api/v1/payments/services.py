from dataclasses import dataclass
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from app.api.v1.orders.models import Order, OutboxEvent
from app.api.v1.payments.models import Payment, ProcessedWebhookEvent
from app.api.v1.payments.exceptions import (
    InvalidPaymentWebhookError, PaymentNotFoundError, InvalidOrderForPaymentError,
    OrderNotFoundError,
)

User = get_user_model()


@dataclass(frozen=True, slots=True)
class WebhookProcessingResult:
    processed: bool
    payment: Payment | None


def create_payment_for_order(
    *,
    user: User,
    order_id: int,
    provider: str = Payment.Provider.MOCK,
) -> Payment:
    """
    Создает платеж для существующего заказа.
    Если заказ уже оплачен, возвращает существующий платеж.
    """
    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .filter(id=order_id, user=user)
            .first()
        )
        if order is None:
            raise OrderNotFoundError("Order not found")

        if order.status != Order.Status.CREATED:
            raise InvalidOrderForPaymentError(
                f"Cannot create payment for order with status '{order.status}'."
            )

        if order.total_cents < 0:
            raise InvalidOrderForPaymentError(
                "Cannot create payment for order with zero or negative total."
            )

        existing_payment = (
            Payment.objects
            .select_for_update()
            .filter(order=order)
            .first()
        )

        if existing_payment is not None:
            return existing_payment

        payment = Payment.objects.create(
            order=order,
            provider=provider,
            provider_payment_id=_build_provider_payment_id(provider=provider),
            status=Payment.Status.CREATED,
            amount_cents=order.total_cents,
            currency=order.currency,
        )

        OutboxEvent.objects.create(
            topic="payment.created",
            payload={
                "payment_id": payment.id,
                "order_id": order.id,
                "user_id": user.id,
                "provider": provider,
                "provider_payment_id": payment.provider_payment_id,
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "status": payment.status,
            },
        )

    return payment


def process_payment_webhook(
    *,
    provider: str,
    event_id: str,
    payload: dict,
) -> WebhookProcessingResult:
    normalized_provider = provider.strip().lower()
    normalized_event_id = event_id.strip()

    if not normalized_provider:
        raise InvalidPaymentWebhookError("Webhook provider cannot be empty")

    if not normalized_event_id:
        raise InvalidPaymentWebhookError("Webhook event_id cannot be empty")

    provider_payment_id = payload.get("provider_payment_id")
    if not provider_payment_id:
        raise InvalidPaymentWebhookError(
            "Webhook payload must contain provider_payment_id."
        )

    target_status = _extract_payment_status_from_payload(payload=payload)

    with transaction.atomic():
        try:
            webhook_event, created = ProcessedWebhookEvent.objects.get_or_create(
                provider=normalized_provider,
                event_id=normalized_event_id,
                defaults={
                    "payload": payload
                },
            )
        except IntegrityError as e:
            raise InvalidPaymentWebhookError(
                "Webhook event could not be stored."
            ) from e

        payment = (
            Payment.objects
            .select_for_update()
            .select_related("order", "order__user")
            .filter(
                provider=normalized_provider,
                provider_payment_id=provider_payment_id,
            )
            .first()
        )

        if payment is None:
            raise PaymentNotFoundError(
                f"Payment with provider_payment_id='{provider_payment_id}' was not found."
            )

        if not created:
            return WebhookProcessingResult(
                processed=False,
                payment=payment,
            )

        if target_status == Payment.Status.SUCCEEDED:
            _mark_payment_succeeded(payment)

        elif target_status == Payment.Status.FAILED:
            _mark_payment_failed(payment)

        elif target_status == Payment.Status.CANCELED:
            _mark_payment_canceled(payment)

        else:
            raise InvalidPaymentWebhookError(
                f"Unsupported payment status '{target_status}'."
            )

        payment.refresh_from_db()

        return WebhookProcessingResult(
            processed=True,
            payment=payment,
        )


def _mark_payment_succeeded(payment: Payment) -> None:
    if payment.status == Payment.Status.SUCCEEDED:
        return

    if payment.status in {Payment.Status.CANCELED, Payment.Status.FAILED}:
        raise InvalidPaymentWebhookError(
            f"Cannot mark payment as succeeded from status '{payment.status}'."
        )

    order = payment.order

    if order.status == Order.Status.CANCELED:
        raise InvalidPaymentWebhookError(
            "Cannot mark payment as succeeded for canceled order."
        )

    payment.status = Payment.Status.SUCCEEDED
    payment.save(update_fields=["status", "updated_at"])

    if order.status != Order.Status.PAID:
        order.status = Order.Status.PAID
        order.save(update_fields=["status"])

    OutboxEvent.objects.create(
        topic="payment.succeeded",
        payload={
            "payment_id": payment.id,
            "order_id": order.id,
            "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
            "amount_cents": payment.amount_cents,
            "currency": payment.currency,
        },
    )

    OutboxEvent.objects.create(
        topic="order.paid",
        payload={
            "order_id": order.id,
            "user_id": order.user_id,
            "payment_id": payment.id,
            "total_cents": order.total_cents,
            "currency": order.currency,
        }
    )


def _mark_payment_failed(payment: Payment) -> None:
    if payment.status == Payment.Status.FAILED:
        return

    if payment.status == Payment.Status.SUCCEEDED:
        raise InvalidPaymentWebhookError(
            "Cannot mark succeeded payment as failed."
        )

    payment.status = Payment.Status.FAILED
    payment.save(update_fields=["status", "updated_at"])

    OutboxEvent.objects.create(
        topic="payment.failed",
        payload={
            "payment_id": payment.id,
            "order_id": payment.order_id,
            "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
        },
    )


def _mark_payment_canceled(payment: Payment) -> None:
    if payment.status == Payment.Status.CANCELED:
        return

    if payment.status == Payment.Status.SUCCEEDED:
        raise InvalidPaymentWebhookError(
            "Cannot cancel succeeded payment."
        )

    payment.status = Payment.Status.CANCELED
    payment.save(update_fields=["status", "updated_at"])

    OutboxEvent.objects.create(
        topic="payment.canceled",
        payload={
            "payment_id": payment.id,
            "order_id": payment.order_id,
            "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
        },
    )


def _extract_payment_status_from_payload(*, payload: dict) -> str:
    event_type = payload.get("type")
    status = payload.get("status")

    if event_type == "payment.succeeded":
        return Payment.Status.SUCCEEDED

    if event_type == "payment.failed":
        return Payment.Status.FAILED

    if event_type == "payment.canceled":
        return Payment.Status.CANCELED

    if status in (
        Payment.Status.SUCCEEDED,
        Payment.Status.FAILED,
        Payment.Status.CANCELED,
    ):
        return status

    raise InvalidPaymentWebhookError(
        "Webhook payload must contain valid type or status."
    )


def _build_provider_payment_id(*, provider: str) -> str:
    return f"{provider}_{uuid4().hex}"
