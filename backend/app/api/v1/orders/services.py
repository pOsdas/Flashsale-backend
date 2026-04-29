from dataclasses import dataclass
from typing import Iterable, Type
import hashlib
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet

from app.api.v1.orders.exceptions import (
    ProductNotFoundError, UnsupportedCurrencyError, OrderNotFoundError, InvalidOrderStatusTransitionError,
    IdempotencyConflictError, IdempotencyResultCorruptedError, EmptyOrderError, InsufficientStockError,
    InvalidOrderItemQuantityError, ProductInactiveError,
)
from app.api.v1.catalog.models import Stock
from app.api.v1.orders.models import Order, OrderItem, OutboxEvent, IdempotencyKey

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
    """
    Создаёт заказ, позиции заказа и уменьшает остатки на складе.

    Алгоритм:
    1. Валидируем входные данные.
    2. Блокируем строки Stock через select_for_update().
    3. Проверяем доступность товара.
    4. Считаем total_cents.
    5. Создаём Order и OrderItem.
    6. Уменьшаем остатки.
    """

    normalized_items = _normalized_items(items)

    if currency != "EUR":
        raise UnsupportedCurrencyError("Only EUR currency is supported now.")

    if not idempotency_key.strip():
        raise IdempotencyConflictError("Idempotency key cannot be empty.")

    payload_hash = _build_order_payload_hash(
        currency=currency,
        items=normalized_items,
    )

    with transaction.atomic():
        existing_key = (
            IdempotencyKey.objects
            .select_for_update()
            .filter(user=user, key=idempotency_key)
            .first()
        )

        if existing_key is not None:
            if existing_key.payload_hash != payload_hash:
                raise IdempotencyConflictError(
                    "This idempotency key was already used with another payload."
                )

            order_id = (existing_key.response_json or {}).get("order_id")
            if order_id is None:
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
                raise ProductNotFoundError(
                    f"Product with id={item.product_id} was not found in stock."
                )

            product = stock.product
            if not product.is_active:
                raise ProductInactiveError(
                    f"Product with id={product.id} is inactive."
                )

            if stock.available < item.qty:
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

        OutboxEvent.objects.create(
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


def _normalized_items(items: Iterable[CreateOrderItemInput]) -> list[CreateOrderItemInput]:
    normalized_items = list(items)

    if not normalized_items:
        raise EmptyOrderError("Order items cannot be empty.")

    for item in normalized_items:
        if item.qty <= 0:
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
    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .filter(id=order_id, user=user)
            .first()
        )

        if order is None:
            raise OrderNotFoundError("Order not found.")

        current_status = order.status

        allowed_statuses = ALLOWED_ORDER_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_statuses:
            raise InvalidOrderStatusTransitionError(
                f"Cannot change order status from '{current_status}' to '{new_status}'."
            )

        order.status = new_status
        order.save(update_fields=["status"])

        OutboxEvent.objects.create(
            topic="order.status_changed",
            payload={
                "order_id": order.id,
                "user_id": user.id,
                "old_status": current_status,
                "new_status": order.status,
            },
        )

        return order


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


def _build_order_payload_hash(
    *,
    currency: str,
    items: list[CreateOrderItemInput],
) -> str:
    payload = {
        "currency": currency,
        "items": [
            {
                "product_id": item.product_id,
                "qty": item.qty,
            }
            for item in items
        ],
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
