import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app.core.logging import get_logger
from app.api.v1.payments.exceptions import (
    InvalidPaymentWebhookError,
    PaymentNotFoundError,
)
from app.api.v1.payments.services import process_payment_webhook

logger = get_logger(__name__)


@csrf_exempt
@require_POST
def payment_webhook_view(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        logger.error(
            "Invalid payment webhook JSON payload",
            extra={
                "body": request.body.decode("utf-8", errors="replace"),
            },
        )
        return JsonResponse(
            {"error": "Invalid JSON payload."},
            status=400,
        )

    provider = body.get("provider")
    event_id = body.get("event_id")
    payload = body.get("payload")

    if not provider:
        logger.error(
            "Payment webhook provider is missing",
            extra={
                "event_id": event_id,
                "payload": payload,
            },
        )
        return JsonResponse(
            {"error": "Field 'provider' is required."},
            status=400,
        )

    if not event_id:
        logger.error(
            "Payment webhook event_id is missing",
            extra={
                "provider": provider,
                "payload": payload,
            },
        )
        return JsonResponse(
            {"error": "Field 'event_id' is required."},
            status=400,
        )

    if payload is None:
        logger.error(
            "Payment webhook payload is missing",
            extra={
                "provider": provider,
                "event_id": event_id,
            },
        )
        return JsonResponse(
            {"error": "Field 'payload' is required."},
            status=400,
        )

    try:
        result = process_payment_webhook(
            provider=provider,
            event_id=event_id,
            payload=payload,
        )
    except (InvalidPaymentWebhookError, PaymentNotFoundError) as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
        )
    except Exception:
        logger.error(
            "Unexpected payment webhook view error",
            extra={
                "provider": provider,
                "event_id": event_id,
                "payload": payload,
            },
            exc_info=True,
        )
        return JsonResponse(
            {"error": "Internal server error."},
            status=500,
        )

    if not result.processed:
        return JsonResponse(
            {
                "status": "ignored",
                "message": "Webhook event was already processed.",
            },
            status=200,
        )

    if result.payment is None:
        return JsonResponse(
            {
                "status": "processed",
                "payment": None,
            },
            status=200,
        )

    payment = result.payment

    return JsonResponse(
        {
            "status": "processed",
            "payment_id": payment.id,
            "provider_payment_id": payment.provider_payment_id,
            "payment_status": payment.status,
            "order_id": payment.order_id,
        },
        status=200,
    )