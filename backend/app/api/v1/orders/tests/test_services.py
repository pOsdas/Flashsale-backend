from django.test import TestCase
from django.contrib.auth import get_user_model

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.orders.models import Order, OrderItem, OutboxEvent, IdempotencyKey
from app.api.v1.orders.services import (
    CreateOrderItemInput,
    EmptyOrderError,
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidOrderItemQuantityError,
    InvalidOrderStatusTransitionError,
    ProductInactiveError,
    ProductNotFoundError,
    create_order,
    change_order_status,
)

User = get_user_model()


class OrderServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )

        self.product_1 = Product.objects.create(
            sku="TSHIRT-BLACK-S",
            title="Product1",
            price_cents=1000,
            is_active=True,
        )
        self.product_2 = Product.objects.create(
            sku="TSHIRT-BLACK-M",
            title="Product2",
            price_cents=2500,
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            sku="TSHIRT-BLACK-L",
            title="Inactive Product",
            price_cents=3000,
            is_active=False,
        )

        self.stock_1 = Stock.objects.create(
            product=self.product_1,
            available=10,
        )
        self.stock_2 = Stock.objects.create(
            product=self.product_2,
            available=5,
        )
        self.inactive_stock = Stock.objects.create(
            product=self.inactive_product,
            available=10,
        )

    def test_create_order_success(self):
        order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="order-success-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=2),
                CreateOrderItemInput(product_id=self.product_2.id, qty=1),
            ],
        )

        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, Order.Status.CREATED)
        self.assertEqual(order.currency, "EUR")
        self.assertEqual(order.total_cents, 4500)

        order_items = list(
            OrderItem.objects.filter(order=order).order_by("product_id")
        )
        self.assertEqual(len(order_items), 2)

        self.assertEqual(order_items[0].product_id, self.product_1.id)
        self.assertEqual(order_items[0].qty, 2)
        self.assertEqual(order_items[0].price_cents, 1000)
        self.assertEqual(order_items[0].line_total_cents, 2000)

        self.assertEqual(order_items[1].product_id, self.product_2.id)
        self.assertEqual(order_items[1].qty, 1)
        self.assertEqual(order_items[1].price_cents, 2500)
        self.assertEqual(order_items[1].line_total_cents, 2500)

        self.stock_1.refresh_from_db()
        self.stock_2.refresh_from_db()

        self.assertEqual(self.stock_1.available, 8)
        self.assertEqual(self.stock_2.available, 4)

        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.created").count(),
            1,
        )

        saved_key = IdempotencyKey.objects.get(
            user=self.user,
            key="order-success-1",
        )
        self.assertEqual(saved_key.response_json["order_id"], order.id)

    def test_create_order_empty_items_raises_error(self):
        with self.assertRaises(EmptyOrderError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="empty-order-1",
                items=[],
            )

    def test_create_order_with_zero_qty_raises_error(self):
        with self.assertRaises(InvalidOrderItemQuantityError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="zero-qty-1",
                items=[
                    CreateOrderItemInput(product_id=self.product_1.id, qty=0),
                ],
            )

    def test_create_order_with_negative_qty_raises_error(self):
        with self.assertRaises(InvalidOrderItemQuantityError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="negative-qty-1",
                items=[
                    CreateOrderItemInput(product_id=self.product_1.id, qty=-1),
                ],
            )

    def test_create_order_with_missing_product_raises_error(self):
        with self.assertRaises(ProductNotFoundError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="missing-product-1",
                items=[
                    CreateOrderItemInput(product_id=999999, qty=1),
                ],
            )

    def test_create_order_with_inactive_product_raises_error(self):
        with self.assertRaises(ProductInactiveError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="inactive-product-1",
                items=[
                    CreateOrderItemInput(product_id=self.inactive_product.id, qty=1),
                ],
            )

    def test_create_order_with_insufficient_stock_raises_error(self):
        with self.assertRaises(InsufficientStockError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="insufficient-stock-1",
                items=[
                    CreateOrderItemInput(product_id=self.product_2.id, qty=999),
                ],
            )

    def test_create_order_same_idempotency_key_same_payload_returns_same_order(self):
        first_order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="same-key-same-payload-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=2),
            ],
        )

        second_order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="same-key-same-payload-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=2),
            ],
        )

        self.assertEqual(first_order.id, second_order.id)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)
        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.created").count(),
            1,
        )

        self.stock_1.refresh_from_db()
        self.assertEqual(self.stock_1.available, 8)

    def test_create_order_same_idempotency_key_different_payload_raises_error(self):
        create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="same-key-different-payload-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=1),
            ],
        )

        with self.assertRaises(IdempotencyConflictError):
            create_order(
                user=self.user,
                currency="EUR",
                idempotency_key="same-key-different-payload-1",
                items=[
                    CreateOrderItemInput(product_id=self.product_1.id, qty=3),
                ],
            )

    def test_change_order_status_created_to_paid_success(self):
        order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="status-paid-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=1),
            ],
        )

        updated_order = change_order_status(
            user=self.user,
            order_id=order.id,
            new_status=Order.Status.PAID,
        )

        self.assertEqual(updated_order.status, Order.Status.PAID)
        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.status_changed").count(),
            1,
        )

    def test_change_order_status_created_to_canceled_success(self):
        order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="status-canceled-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=1),
            ],
        )

        updated_order = change_order_status(
            user=self.user,
            order_id=order.id,
            new_status=Order.Status.CANCELED,
        )

        self.assertEqual(updated_order.status, Order.Status.CANCELED)
        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.status_changed").count(),
            1,
        )

    def test_change_order_status_paid_to_canceled_raises_error(self):
        order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="status-paid-to-canceled-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=1),
            ],
        )

        change_order_status(
            user=self.user,
            order_id=order.id,
            new_status=Order.Status.PAID,
        )

        with self.assertRaises(InvalidOrderStatusTransitionError):
            change_order_status(
                user=self.user,
                order_id=order.id,
                new_status=Order.Status.CANCELED,
            )

    def test_change_order_status_canceled_to_paid_raises_error(self):
        order = create_order(
            user=self.user,
            currency="EUR",
            idempotency_key="status-canceled-to-paid-1",
            items=[
                CreateOrderItemInput(product_id=self.product_1.id, qty=1),
            ],
        )

        change_order_status(
            user=self.user,
            order_id=order.id,
            new_status=Order.Status.CANCELED,
        )

        with self.assertRaises(InvalidOrderStatusTransitionError):
            change_order_status(
                user=self.user,
                order_id=order.id,
                new_status=Order.Status.PAID,
            )
