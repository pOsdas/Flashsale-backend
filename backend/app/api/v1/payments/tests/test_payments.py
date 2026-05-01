from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.orders.models import Order, OrderItem, OutboxEvent
from app.api.v1.payments.exceptions import (
    InvalidPaymentWebhookError,
    OrderNotFoundError,
    PaymentNotFoundError,
)
from app.api.v1.payments.models import Payment, ProcessedWebhookEvent
from app.api.v1.payments.services import (
    create_payment_for_order,
    process_payment_webhook,
)

User = get_user_model()


class PaymentsServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        self.product = Product.objects.create(
            sku="TEST-1",
            title="Test product",
            price_cents=1000,
            currency="USD",
            is_active=True,
        )

        self.stock = Stock.objects.create(
            product=self.product,
            available=10,
        )

        self.order = Order.objects.create(
            user=self.user,
            status=Order.Status.CREATED,
        )

        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            qty=2,
            price_cents=self.product.price_cents,
            line_total_cents=self.product.price_cents * 2,
        )

    def create_payment(self):
        return create_payment_for_order(
            user=self.user,
            order_id=self.order.id,
            provider=Payment.Provider.MOCK,
        )

    def test_create_payment_for_order(self):
        payment = self.create_payment()

        self.assertIsInstance(payment, Payment)
        self.assertEqual(payment.order_id, self.order.id)
        self.assertEqual(payment.provider, Payment.Provider.MOCK)
        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertEqual(Payment.objects.count(), 1)

        event = OutboxEvent.objects.get(
            topic="payment.created",
        )

        self.assertEqual(event.payload["order_id"], self.order.id)
        self.assertEqual(event.payload["payment_id"], payment.id)

    def test_create_payment_for_order_invalid_order_id_raises_error(self):
        with self.assertRaises(OrderNotFoundError):
            create_payment_for_order(
                user=self.user,
                order_id=999999,
                provider=Payment.Provider.MOCK,
            )

    def test_process_payment_webhook_succeeded_marks_payment_and_order_paid(self):
        payment = self.create_payment()

        result = process_payment_webhook(
            provider=Payment.Provider.MOCK,
            event_id="evt_payment_succeeded_1",
            payload={
                "provider_payment_id": payment.provider_payment_id,
                "status": "succeeded",
            },
        )

        self.assertTrue(result.processed)
        self.assertIsNotNone(result.payment)

        payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)

        self.assertTrue(
            ProcessedWebhookEvent.objects.filter(
                provider=Payment.Provider.MOCK,
                event_id="evt_payment_succeeded_1",
            ).exists()
        )

        payment_succeeded_event = OutboxEvent.objects.get(
            topic="payment.succeeded",
        )

        order_paid_event = OutboxEvent.objects.get(
            topic="order.paid",
        )

        self.assertEqual(payment_succeeded_event.payload["payment_id"], payment.id)
        self.assertEqual(payment_succeeded_event.payload["order_id"], self.order.id)

        self.assertEqual(order_paid_event.payload["order_id"], self.order.id)
        self.assertEqual(order_paid_event.payload["payment_id"], payment.id)

    def test_process_payment_webhook_failed_marks_payment_failed_but_order_not_paid(self):
        payment = self.create_payment()

        result = process_payment_webhook(
            provider=Payment.Provider.MOCK,
            event_id="evt_payment_failed_1",
            payload={
                "provider_payment_id": payment.provider_payment_id,
                "status": "failed",
            },
        )

        self.assertTrue(result.processed)
        self.assertIsNotNone(result.payment)

        payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertNotEqual(self.order.status, Order.Status.PAID)

        self.assertTrue(
            ProcessedWebhookEvent.objects.filter(
                provider=Payment.Provider.MOCK,
                event_id="evt_payment_failed_1",
            ).exists()
        )

        payment_failed_event = OutboxEvent.objects.get(
            topic="payment.failed",
        )

        self.assertEqual(payment_failed_event.payload["payment_id"], payment.id)
        self.assertEqual(payment_failed_event.payload["order_id"], self.order.id)

        self.assertFalse(
            OutboxEvent.objects.filter(
                topic="order.paid",
            ).exists()
        )

    def test_process_payment_webhook_canceled_marks_payment_canceled_but_order_not_paid(self):
        payment = self.create_payment()

        result = process_payment_webhook(
            provider=Payment.Provider.MOCK,
            event_id="evt_payment_canceled_1",
            payload={
                "provider_payment_id": payment.provider_payment_id,
                "status": "canceled",
            },
        )

        self.assertTrue(result.processed)
        self.assertIsNotNone(result.payment)

        payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.CANCELED)
        self.assertNotEqual(self.order.status, Order.Status.PAID)

        self.assertTrue(
            ProcessedWebhookEvent.objects.filter(
                provider=Payment.Provider.MOCK,
                event_id="evt_payment_canceled_1",
            ).exists()
        )

        payment_canceled_event = OutboxEvent.objects.get(
            topic="payment.canceled",
        )

        self.assertEqual(payment_canceled_event.payload["payment_id"], payment.id)
        self.assertEqual(payment_canceled_event.payload["order_id"], self.order.id)

        self.assertFalse(
            OutboxEvent.objects.filter(
                topic="order.paid",
            ).exists()
        )

    def test_process_payment_webhook_idempotency(self):
        payment = self.create_payment()

        first_result = process_payment_webhook(
            provider=Payment.Provider.MOCK,
            event_id="evt_payment_succeeded_1",
            payload={
                "provider_payment_id": payment.provider_payment_id,
                "status": "succeeded",
            },
        )

        self.assertTrue(first_result.processed)
        self.assertIsNotNone(first_result.payment)

        second_result = process_payment_webhook(
            provider=Payment.Provider.MOCK,
            event_id="evt_payment_succeeded_1",
            payload={
                "provider_payment_id": payment.provider_payment_id,
                "status": "succeeded",
            },
        )

        self.assertFalse(second_result.processed)
        self.assertIsNotNone(second_result.payment)
        self.assertEqual(second_result.payment.id, payment.id)

        self.assertEqual(
            OutboxEvent.objects.filter(topic="payment.succeeded").count(),
            1,
        )

        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.paid").count(),
            1,
        )

        self.assertEqual(
            ProcessedWebhookEvent.objects.filter(
                provider=Payment.Provider.MOCK,
                event_id="evt_payment_succeeded_1",
            ).count(),
            1,
        )

    def test_process_payment_webhook_without_payment_id_raises_error(self):
        with self.assertRaises(InvalidPaymentWebhookError):
            process_payment_webhook(
                provider=Payment.Provider.MOCK,
                event_id="evt_invalid_without_payment_id",
                payload={
                    "status": "succeeded",
                },
            )

        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                event_id="evt_invalid_without_payment_id",
            ).exists()
        )

    def test_process_payment_webhook_without_status_raises_error(self):
        payment = self.create_payment()

        with self.assertRaises(InvalidPaymentWebhookError):
            process_payment_webhook(
                provider=Payment.Provider.MOCK,
                event_id="evt_invalid_without_status",
                payload={
                    "provider_payment_id": payment.provider_payment_id,
                },
            )

        payment.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                event_id="evt_invalid_without_status",
            ).exists()
        )

    def test_process_payment_webhook_with_unknown_status_raises_error(self):
        payment = self.create_payment()

        with self.assertRaises(InvalidPaymentWebhookError):
            process_payment_webhook(
                provider=Payment.Provider.MOCK,
                event_id="evt_invalid_unknown_status",
                payload={
                    "provider_payment_id": payment.provider_payment_id,
                    "status": "refunded",
                },
            )

        payment.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                event_id="evt_invalid_unknown_status",
            ).exists()
        )

    def test_process_payment_webhook_with_unknown_payment_id_raises_error(self):
        with self.assertRaises(PaymentNotFoundError):
            process_payment_webhook(
                provider=Payment.Provider.MOCK,
                event_id="evt_unknown_payment",
                payload={
                    "provider_payment_id": "unknown-provider-payment-id",
                    "status": "succeeded",
                },
            )

        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                event_id="evt_unknown_payment",
            ).exists()
        )

    def test_process_payment_webhook_is_transactional_when_outbox_creation_fails(self):
        payment = self.create_payment()

        initial_processed_webhook_count = ProcessedWebhookEvent.objects.count()
        initial_payment_succeeded_count = OutboxEvent.objects.filter(
            topic="payment.succeeded",
        ).count()

        with patch(
            "app.api.v1.payments.services.OutboxEvent.objects.create",
            side_effect=RuntimeError("Outbox failure"),
        ):
            with self.assertRaises(RuntimeError):
                process_payment_webhook(
                    provider=Payment.Provider.MOCK,
                    event_id="evt_transaction_error",
                    payload={
                        "provider_payment_id": payment.provider_payment_id,
                        "status": "succeeded",
                    },
                )

        payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(payment.status, Payment.Status.CREATED)
        self.assertEqual(self.order.status, Order.Status.CREATED)

        self.assertEqual(
            ProcessedWebhookEvent.objects.count(),
            initial_processed_webhook_count,
        )

        self.assertEqual(
            OutboxEvent.objects.filter(topic="payment.succeeded").count(),
            initial_payment_succeeded_count,
        )

        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                event_id="evt_transaction_error",
            ).exists()
        )


class PaymentsWebhookViewTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )

        self.product = Product.objects.create(
            sku="TEST-1",
            title="Test product",
            price_cents=1000,
            currency="USD",
            is_active=True,
        )

        self.stock = Stock.objects.create(
            product=self.product,
            available=10,
        )

        self.order = Order.objects.create(
            user=self.user,
            status=Order.Status.CREATED,
        )

        self.order_item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            qty=2,
            price_cents=self.product.price_cents,
            line_total_cents=self.product.price_cents * 2,
        )

        self.payment = create_payment_for_order(
            user=self.user,
            order_id=self.order.id,
            provider=Payment.Provider.MOCK,
        )

        self.url = "/api/v1/payments/webhook/"

    def test_payment_webhook_view_success(self):
        response = self.client.post(
            self.url,
            data={
                "provider": Payment.Provider.MOCK,
                "event_id": "evt_view_success_1",
                "payload": {
                    "provider_payment_id": self.payment.provider_payment_id,
                    "status": "succeeded",
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["status"], "processed")
        self.assertEqual(data["payment_id"], self.payment.id)
        self.assertEqual(data["payment_status"], Payment.Status.SUCCEEDED)
        self.assertEqual(data["order_id"], self.order.id)

        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_payment_webhook_view_duplicate_is_ignored(self):
        payload = {
            "provider": Payment.Provider.MOCK,
            "event_id": "evt_view_duplicate_1",
            "payload": {
                "provider_payment_id": self.payment.provider_payment_id,
                "status": "succeeded",
            },
        }

        first_response = self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

        second_response = self.client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        data = second_response.json()

        self.assertEqual(data["status"], "ignored")

        self.assertEqual(
            OutboxEvent.objects.filter(topic="payment.succeeded").count(),
            1,
        )

        self.assertEqual(
            OutboxEvent.objects.filter(topic="order.paid").count(),
            1,
        )

    def test_payment_webhook_view_requires_post(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_payment_webhook_view_invalid_json(self):
        response = self.client.post(
            self.url,
            data="{invalid json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON payload.")

    def test_payment_webhook_view_without_provider_returns_400(self):
        response = self.client.post(
            self.url,
            data={
                "event_id": "evt_without_provider",
                "payload": {
                    "payment_id": self.payment.id,
                    "status": "succeeded",
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Field 'provider' is required.")

    def test_payment_webhook_view_without_event_id_returns_400(self):
        response = self.client.post(
            self.url,
            data={
                "provider": Payment.Provider.MOCK,
                "payload": {
                    "payment_id": self.payment.provider_payment_id,
                    "status": "succeeded",
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Field 'event_id' is required.")

    def test_payment_webhook_view_without_payload_returns_400(self):
        response = self.client.post(
            self.url,
            data={
                "provider": Payment.Provider.MOCK,
                "event_id": "evt_without_payload",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Field 'payload' is required.")

    def test_payment_webhook_view_invalid_payload_returns_400(self):
        response = self.client.post(
            self.url,
            data={
                "provider": Payment.Provider.MOCK,
                "event_id": "evt_invalid_payload",
                "payload": {
                    "payment_id": self.payment.provider_payment_id,
                    "status": "unknown",
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)