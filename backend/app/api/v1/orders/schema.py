from typing import List, Optional
from enum import Enum
import strawberry
from graphql import GraphQLError
from strawberry import auto
from strawberry.types import Info
from strawberry_django import type as dj_type
from django.contrib.auth import get_user_model
from django.db import transaction

from app.api.v1.orders.models import (
    Reservation,
    Order,
    OrderItem,
    IdempotencyKey,
    OutboxEvent,
)
from app.api.v1.orders.services import (
    CreateOrderItemInput,
    EmptyOrderError,
    OrderServiceError,
    ProductInactiveError,
    InsufficientStockError,
    InvalidOrderItemQuantityError,
    ProductNotFoundError,
    UnsupportedCurrencyError,
    OrderNotFoundError,
    InvalidOrderStatusTransitionError,
    IdempotencyConflictError,
    IdempotencyResultCorruptedError,
    create_order,
    change_order_status,
)
from app.api.v1.catalog.schema import ProductType

User = get_user_model()


# ---- Enums ----
@strawberry.enum
class OrderStatusEnum(str, Enum):
    CREATED = "created"
    PAID = "paid"
    CANCELED = "canceled"


# ---- Types ----
@dj_type(Reservation)
class ReservationType:
    id: auto
    user: auto
    product: auto
    qty: auto
    created_at: auto


@dj_type(OrderItem)
class OrderItemType:
    id: auto
    order: auto
    product: ProductType
    qty: auto
    price_cents: auto
    line_total_cents: auto


@dj_type(Order)
class OrderType:
    id: auto
    user: auto
    status: auto
    total_cents: auto
    currency: auto
    created_at: auto

    items: List[OrderItemType]


@dj_type(IdempotencyKey)
class IdempotencyKeyType:
    id: auto
    user: auto
    key: auto
    payload_hash: auto
    response_json: auto
    created_at: auto


@dj_type(OutboxEvent)
class OutboxEventType:
    id: auto
    topic: auto
    payload: auto
    created_at: auto
    published_at: auto


# ---- Query ----
@strawberry.type
class OrdersQuery:

    @strawberry.field
    def my_orders(self, info: Info) -> List["OrderType"]:
        user = info.context.request.user
        return list(
            Order.objects
            .filter(user=user)
            .select_related("user")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

    @strawberry.field
    def order(self, info: Info, order_id: int) -> Optional["OrderType"]:
        user = info.context.request.user

        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        return (
            Order.objects
            .filter(id=order_id, user=user)
            .select_related("user")
            .prefetch_related("items__product")
            .first()
        )

    @strawberry.field
    def reservation(self, info: Info) -> List[ReservationType]:
        user = info.context.request.user

        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        return list(
            Reservation.objects
            .filter(user=user)
            .select_related("product")
            .order_by("-created_at")
        )


# ---- Inputs ----
@strawberry.input
class OrderItemInput:
    product_id: int
    qty: int


@strawberry.input
class CreateOrderInput:
    items: List[OrderItemInput]
    currency: str = "EUR"
    idempotency_key: str


# ---- Mutations ----
@strawberry.type
class OrdersMutation:

    @strawberry.mutation
    @transaction.atomic
    def create_order(self, info: Info, data: CreateOrderInput) -> OrderType:
        user = info.context.request.user

        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        if data.currency != "EUR":
            raise GraphQLError("Only EUR currency is supported now.")

        service_items = [
            CreateOrderItemInput(
                product_id=item.product_id,
                qty=item.qty,
            )
            for item in data.items
        ]
        try:
            order = create_order(
                user=user,
                items=service_items,
                currency=data.currency,
                idempotency_key=data.idempotency_key,
            )
        except EmptyOrderError as e:
            raise GraphQLError(str(e))
        except InvalidOrderItemQuantityError as e:
            raise GraphQLError(str(e))
        except ProductNotFoundError as e:
            raise GraphQLError(str(e))
        except ProductInactiveError as e:
            raise GraphQLError(str(e))
        except InsufficientStockError as e:
            raise GraphQLError(str(e))
        except UnsupportedCurrencyError as e:
            raise GraphQLError(str(e))
        except IdempotencyConflictError as e:
            raise GraphQLError(str(e))
        except IdempotencyResultCorruptedError as e:
            raise GraphQLError(str(e))
        except InvalidOrderStatusTransitionError as e:
            raise GraphQLError(str(e))
        except OrderServiceError as e:
            raise GraphQLError(str(e))

        return (
            Order.objects
            .select_related("user")
            .prefetch_related("items__product")
            .get(id=order.id)
        )

    @strawberry.mutation
    @transaction.atomic
    def set_order_status(
            self,
            info: Info,
            order_id: int,
            status: OrderStatusEnum,
    ) -> OrderType:
        user = info.context.request.user

        if not user.is_authenticated:
            raise GraphQLError("Authentication required.")

        try:
            order = change_order_status(
                user=user,
                order_id=order_id,
                new_status=status.value,
            )
        except OrderNotFoundError as e:
            raise GraphQLError(str(e))
        except OrderServiceError as e:
            raise GraphQLError(str(e))

        return (
            Order.objects
            .select_related("user")
            .prefetch_related("items__product")
            .get(id=order.id)
        )
