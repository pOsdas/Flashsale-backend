from dataclasses import dataclass
from typing import Iterable, Dict, Type

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet

from app.core.logging import get_logger
from app.api.v1.orders.exceptions import (
    ProductNotFoundError, UnsupportedCurrencyError, OrderNotFoundError, InvalidOrderStatusTransitionError,
    IdempotencyConflictError, IdempotencyResultCorruptedError, EmptyOrderError, InsufficientStockError,
    InvalidOrderItemQuantityError, ProductInactiveError,
)
from app.api.v1.catalog.models import Stock
from app.api.v1.orders.models import Order, OrderItem, IdempotencyKey
from app.api.v1.common.outbox import create_outbox_event
from app.api.v1.common import compare_idempotency_payloads, make_idempotency_hash

logger = get_logger(__name__)
User = get_user_model()


@dataclass(frozen=True, slots=True)
class CreateOrderItemInput:
    product_id: int
    qty: int


ALLOWED_ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    Order.Status.CREATED: {
        Order.Status.PAID,
        Order.Status.CANCELED,
    },
    Order.Status.PAID: set(),
    Order.Status.CANCELED: set(),
}


def create_order(
        *,
        user,
        items: Iterable[CreateOrderItemInput],
        currency: str = "EUR",
        idempotency_key: str,
) -> Order:
    normalized_items = _normalized_items(items)

    if currency not in ["EUR", "RUB"]:
        logger.error(
            "Unsupported order currency",
            extra={
                "user_id": user.id,
                "currency": currency,
                "supported_currency": "EUR, RUB",
            },
        )
        raise UnsupportedCurrencyError("Only EUR, RUB currency is supported now.")

    if not idempotency_key.strip():
        logger.error(
            "Empty idempotency key",
            extra={
                "user_id": user.id,
                "currency": currency,
                "items": [
                    {
                        "product_id": item.product_id,
                        "qty": item.qty,
                    }
                    for item in normalized_items
                ],
            },
        )
        raise IdempotencyConflictError("Idempotency key cannot be empty.")

    payload = _build_order_payload(
        currency=currency,
        items=normalized_items,
    )

    payload_hash = make_idempotency_hash(payload)

    try:
        with transaction.atomic():
            existing_key = (
                IdempotencyKey.objects
                .select_for_update()
                .filter(user=user, key=idempotency_key)
                .first()
            )

            if existing_key is not None:
                if not compare_idempotency_payloads(
                    original_payload_hash=existing_key.payload_hash,
                    current_payload=payload,
                ):
                    logger.error(
                        "Idempotency key payload conflict",
                        extra={
                            "user_id": user.id,
                            "idempotency_key": idempotency_key,
                            "payload": payload,
                        },
                    )
                    raise IdempotencyConflictError(
                        "This idempotency key was already used with another payload."
                    )

                order_id = (existing_key.response_json or {}).get("order_id")
                if order_id is None:
                    logger.error(
                        "Idempotency result does not contain order_id",
                        extra={
                            "user_id": user.id,
                            "idempotency_key": idempotency_key,
                            "response_json": existing_key.response_json,
                        },
                    )
                    raise IdempotencyResultCorruptedError(
                        "Stored idempotency result does not contain order_id."
                    )

                order = (
                    Order.objects
                    .select_related("user")
                    .prefetch_related("items__product")
                    .filter(id=order_id, user=user)
                    .first()
                )

                if order is None:
                    logger.error(
                        "Idempotency result points to missing order",
                        extra={
                            "user_id": user.id,
                            "idempotency_key": idempotency_key,
                            "order_id": order_id,
                        },
                    )
                    raise IdempotencyResultCorruptedError(
                        "Stored idempotency result points to a missing order."
                    )

                return order

            stocks = _get_locked_stocks_by_product_id(normalized_items)

            total_cents = 0
            order = Order.objects.create(
                user=user,
                status=Order.Status.CREATED,
                total_cents=0,
                currency=currency,
            )

            order_items_to_create: list[OrderItem] = []
            stocks_to_update: list[Stock] = []

            for item in normalized_items:
                stock = stocks.get(item.product_id)
                if stock is None:
                    logger.error(
                        "Product stock not found while creating order",
                        extra={
                            "user_id": user.id,
                            "order_id": order.id,
                            "product_id": item.product_id,
                            "qty": item.qty,
                        },
                    )
                    raise ProductNotFoundError(
                        f"Product with id={item.product_id} was not found in stock."
                    )

                product = stock.product
                if not product.is_active:
                    logger.error(
                        "Inactive product used while creating order",
                        extra={
                            "user_id": user.id,
                            "order_id": order.id,
                            "product_id": product.id,
                            "sku": product.sku,
                        },
                    )
                    raise ProductInactiveError(
                        f"Product with id={product.id} is inactive."
                    )

                if stock.available < item.qty:
                    logger.error(
                        "Insufficient stock while creating order",
                        extra={
                            "user_id": user.id,
                            "order_id": order.id,
                            "product_id": product.id,
                            "sku": product.sku,
                            "available": stock.available,
                            "requested": item.qty,
                        },
                    )
                    raise InsufficientStockError(
                        f"Insufficient stock for product id={product.id}. "
                        f"Available: {stock.available}, requested: {item.qty}."
                    )

                line_total_cents = product.price_cents * item.qty
                total_cents += line_total_cents

                order_items_to_create.append(
                    OrderItem(
                        order=order,
                        product=product,
                        qty=item.qty,
                        price_cents=product.price_cents,
                        line_total_cents=line_total_cents,
                    )
                )

                stock.available -= item.qty
                stocks_to_update.append(stock)

            OrderItem.objects.bulk_create(order_items_to_create)

            if stocks_to_update:
                Stock.objects.bulk_update(stocks_to_update, fields=["available"])

            order.total_cents = total_cents
            order.save(update_fields=["total_cents"])

            create_outbox_event(
                topic="order.created",
                payload={
                    "order_id": order.id,
                    "user_id": user.id,
                    "status": order.status,
                    "currency": order.currency,
                    "total_cents": order.total_cents,
                    "items": [
                        {
                            "product_id": item.product_id,
                            "qty": item.qty,
                        }
                        for item in normalized_items
                    ],
                },
            )

            IdempotencyKey.objects.create(
                user=user,
                key=idempotency_key,
                payload_hash=payload_hash,
                response_json={
                    "order_id": order.id,
                },
            )

            return order

    except (
        ProductNotFoundError,
        ProductInactiveError,
        InsufficientStockError,
        IdempotencyConflictError,
        IdempotencyResultCorruptedError,
    ):
        raise
    except Exception:
        logger.error(
            "Unexpected order creation error",
            extra={
                "user_id": user.id,
                "currency": currency,
                "idempotency_key": idempotency_key,
                "items": [
                    {
                        "product_id": item.product_id,
                        "qty": item.qty,
                    }
                    for item in normalized_items
                ],
            },
            exc_info=True,
        )
        raise


def _normalized_items(items: Iterable[CreateOrderItemInput]) -> list[CreateOrderItemInput]:
    normalized_items = list(items)

    if not normalized_items:
        logger.error("Empty order items")
        raise EmptyOrderError("Order items cannot be empty.")

    for item in normalized_items:
        if item.qty <= 0:
            logger.error(
                "Invalid order item quantity",
                extra={
                    "product_id": item.product_id,
                    "qty": item.qty,
                },
            )
            raise InvalidOrderItemQuantityError(
                f"Quantity must be greater than zero for product_id={item.product_id}."
            )

    return normalized_items


def change_order_status(
        *,
        user: User,
        order_id: int,
        new_status: str,
) -> Order:
    try:
        with transaction.atomic():
            order = (
                Order.objects
                .select_for_update()
                .filter(id=order_id, user=user)
                .first()
            )

            if order is None:
                logger.error(
                    "Order not found while changing status",
                    extra={
                        "user_id": user.id,
                        "order_id": order_id,
                        "new_status": new_status,
                    },
                )
                raise OrderNotFoundError("Order not found.")

            current_status = order.status

            allowed_statuses = ALLOWED_ORDER_STATUS_TRANSITIONS.get(current_status, set())
            if new_status not in allowed_statuses:
                logger.error(
                    "Invalid order status transition",
                    extra={
                        "user_id": user.id,
                        "order_id": order.id,
                        "current_status": current_status,
                        "new_status": new_status,
                        "allowed_statuses": list(allowed_statuses),
                    },
                )
                raise InvalidOrderStatusTransitionError(
                    f"Cannot change order status from '{current_status}' to '{new_status}'."
                )

            order.status = new_status
            order.save(update_fields=["status"])

            create_outbox_event(
                topic="order.status_changed",
                payload={
                    "order_id": order.id,
                    "user_id": user.id,
                    "old_status": current_status,
                    "new_status": order.status,
                },
            )

            return order

    except (OrderNotFoundError, InvalidOrderStatusTransitionError):
        raise
    except Exception:
        logger.error(
            "Unexpected order status change error",
            extra={
                "user_id": user.id,
                "order_id": order_id,
                "new_status": new_status,
            },
            exc_info=True,
        )
        raise


def _get_locked_stocks_by_product_id(
        items: list[CreateOrderItemInput],
) -> dict[Type[int], Stock]:
    product_ids = [item.product_id for item in items]

    stocks_qs: QuerySet[Stock] = (
        Stock.objects
        .select_for_update()
        .select_related("product")
        .filter(product_id__in=product_ids)
    )

    return {stock.product_id: stock for stock in stocks_qs}


def _build_order_payload(
    *,
    currency: str,
    items: list[CreateOrderItemInput],
) -> dict:
    return {
        "currency": currency,
        "items": [
            {
                "product_id": item.product_id,
                "qty": item.qty,
            }
            for item in items
        ],
    }


def _build_order_payload_hash(
    *,
    currency: str,
    items: list[CreateOrderItemInput],
) -> str:
    return make_idempotency_hash(
        _build_order_payload(
            currency=currency,
            items=items,
        )
    )
