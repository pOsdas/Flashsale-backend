from unittest.mock import patch

from django.test import TestCase

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.common.locks import RedisLockAlreadyAcquiredError
from app.api.v1.fetcher.exceptions import (
    FetcherBatchAlreadyProcessedError,
    FetcherCurrencyNotSupportedError,
    FetcherImportInProgressError,
)
from app.api.v1.fetcher.services.fetcher_import_service import FetcherImportService
from app.api.v1.orders.models import OutboxEvent
from app.api.v1.payments.models import ProcessedWebhookEvent


class FetcherImportServiceTests(TestCase):
    def setUp(self):
        self.items = [
            {
                "sku": "IPHONE-15",
                "title": "iPhone 15",
                "price_cents": 1000,
                "currency": "EUR",
                "available": 15,
                "is_active": True,
            }
        ]

    def test_service_creates_product_stock_outbox_and_processed_batch(self):
        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-001",
            items=self.items,
        )

        result = service.execute()

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)

        product = Product.objects.get(sku="IPHONE-15")

        self.assertEqual(product.title, "iPhone 15")
        self.assertEqual(product.price_cents, 1000)

        stock = Stock.objects.get(product=product)

        self.assertEqual(stock.available, 15)

        self.assertTrue(
            ProcessedWebhookEvent.objects.filter(
                provider="wildberries",
                event_id="wb-001",
            ).exists()
        )

        outbox_event = OutboxEvent.objects.get(topic="catalog.import.completed")

        self.assertEqual(outbox_event.payload["source"], "wildberries")
        self.assertEqual(outbox_event.payload["batch_id"], "wb-001")
        self.assertEqual(outbox_event.payload["created"], 1)
        self.assertEqual(outbox_event.payload["updated"], 0)

    def test_service_updates_existing_product_and_stock(self):
        product = Product.objects.create(
            sku="IPHONE-15",
            title="Old iPhone",
            price_cents=500,
            currency="EUR",
            is_active=True,
        )
        Stock.objects.create(product=product, available=1)

        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-002",
            items=[
                {
                    "sku": "IPHONE-15",
                    "title": "iPhone 15 Updated",
                    "price_cents": 2000,
                    "currency": "EUR",
                    "available": 25,
                    "is_active": False,
                }
            ],
        )

        result = service.execute()

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)

        product.refresh_from_db()
        self.assertEqual(product.title, "iPhone 15 Updated")
        self.assertEqual(product.price_cents, 2000)
        self.assertFalse(product.is_active)

        stock = Stock.objects.get(product=product)
        self.assertEqual(stock.available, 25)

    def test_service_raises_when_batch_already_processed(self):
        ProcessedWebhookEvent.objects.create(
            provider="wildberries",
            event_id="wb-001",
            payload={"type": "fetcher_import"},
        )

        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-001",
            items=self.items,
        )

        with self.assertRaises(FetcherBatchAlreadyProcessedError):
            service.execute()

        self.assertFalse(Product.objects.filter(sku="IPHONE-15").exists())
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_service_raises_for_unsupported_currency(self):
        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-003",
            items=[
                {
                    "sku": "IPHONE-16",
                    "title": "iPhone 16",
                    "price_cents": 1000,
                    "currency": "USD",
                    "available": 15,
                    "is_active": True,
                }
            ],
        )

        with self.assertRaises(FetcherCurrencyNotSupportedError):
            service.execute()

        self.assertFalse(Product.objects.filter(sku="IPHONE-16").exists())
        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    @patch("app.api.v1.fetcher.services.fetcher_import_service.RedisLock.__enter__")
    def test_service_raises_when_import_already_running(self, enter_mock):
        enter_mock.side_effect = RedisLockAlreadyAcquiredError(
            "Lock already acquired"
        )

        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-004",
            items=self.items,
        )

        with self.assertRaises(FetcherImportInProgressError):
            service.execute()

        self.assertFalse(Product.objects.filter(sku="IPHONE-15").exists())

    def test_service_rolls_back_transaction_when_second_item_fails(self):
        service = FetcherImportService(
            source="wildberries",
            batch_id="wb-005",
            items=[
                {
                    "sku": "IPHONE-15",
                    "title": "iPhone 15",
                    "price_cents": 1000,
                    "currency": "EUR",
                    "available": 15,
                    "is_active": True,
                },
                {
                    "sku": "BAD-ITEM",
                    "title": "Bad Item",
                    "price_cents": 1000,
                    "currency": "USD",
                    "available": 10,
                    "is_active": True,
                },
            ],
        )

        with self.assertRaises(FetcherCurrencyNotSupportedError):
            service.execute()

        self.assertFalse(Product.objects.filter(sku="IPHONE-15").exists())
        self.assertFalse(Product.objects.filter(sku="BAD-ITEM").exists())
        self.assertEqual(Stock.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.count(), 0)

        self.assertFalse(
            ProcessedWebhookEvent.objects.filter(
                provider="wildberries",
                event_id="wb-005",
            ).exists()
        )
