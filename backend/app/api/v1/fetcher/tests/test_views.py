from unittest.mock import patch
from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from django.test import override_settings

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.fetcher.exceptions import FetcherImportInProgressError
from app.api.v1.orders.models import OutboxEvent


@override_settings(fetcher_api_key="test-fetcher-key")
class FetcherViewTests(APITestCase):
    def setUp(self):
        self.payload = {
            "source": "wildberries",
            "batch_id": "wb-001",
            "items": [
                {
                    "sku": "iphone-15",
                    "title": "iPhone 15",
                    "price_cents": 1000,
                    "currency": "EUR",
                    "available": 15,
                    "is_active": True,
                }
            ],
        }

    def test_import_endpoint_creates_product_and_stock_and_outbox_event(self):
        url = reverse("fetcher-import")

        response = self.client.post(
            url,
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        self.assertTrue(response_data["success"])
        self.assertEqual(response_data["status"], "imported")
        self.assertEqual(response_data["created"], 1)
        self.assertEqual(response_data["updated"], 0)

        product = Product.objects.get(sku="IPHONE-15")

        self.assertEqual(product.title, "iPhone 15")
        self.assertEqual(product.price_cents, 1000)

        stock = Stock.objects.get(product=product)

        self.assertEqual(stock.available, 15)

        outbox_event = OutboxEvent.objects.get(topic="catalog.import.completed")

        self.assertEqual(outbox_event.payload["source"], "wildberries")
        self.assertEqual(outbox_event.payload["batch_id"], "wb-001")
        self.assertEqual(outbox_event.payload["created"], 1)
        self.assertEqual(outbox_event.payload["updated"], 0)

    def test_import_endpoint_idempotency(self):
        url = reverse("fetcher-import")

        first_response = self.client.post(
            url,
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.json()["status"], "imported")

        second_response = self.client.post(
            url,
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        response_data = second_response.json()

        self.assertTrue(response_data["success"])
        self.assertEqual(response_data["status"], "already_processed")
        self.assertEqual(response_data["created"], 0)
        self.assertEqual(response_data["updated"], 0)

        self.assertEqual(Product.objects.filter(sku="IPHONE-15").count(), 1)

        product = Product.objects.get(sku="IPHONE-15")
        stock = Stock.objects.get(product=product)

        self.assertEqual(product.title, "iPhone 15")
        self.assertEqual(product.price_cents, 1000)
        self.assertEqual(stock.available, 15)

    def test_import_endpoint_unsupported_currency(self):
        unsupported_currency_payload = {
            "source": "wildberries",
            "batch_id": "wb-001",
            "items": [
                {
                    "sku": "iphone-16",
                    "title": "iPhone 16",
                    "price_cents": 89200,
                    "currency": "RUB",
                    "available": 15,
                    "is_active": True,
                }
            ]
        }

        url = reverse("fetcher-import")

        response = self.client.post(
            url,
            data=unsupported_currency_payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response_data = response.json()

        self.assertFalse(response_data["success"])
        self.assertEqual(response_data["error"], f"Unsupported currency: RUB")

    def test_import_endpoint_invalid_payload(self):
        invalid_payload = {
            "source": "",
            "batch_id": "",
            "items": [
                {
                    "sku": "",
                    "title": "",
                    "price_cents": 1000,
                    "currency": "EUR",
                    "available": 15,
                    "is_active": True,
                }
            ]
        }

        url = reverse("fetcher-import")

        response = self.client.post(
            url,
            data=invalid_payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response_data = response.json()

        self.assertFalse(response_data["success"])
        self.assertEqual(response_data["error"], "Invalid import payload.")

    def test_import_endpoint_returns_400_for_duplicate_sku_inside_items(self):
        sku_idempotency_payload = {
            "source": "wildberries",
            "batch_id": "wb-001",
            "items": [
                {
                    "sku": "iphone-14",
                    "title": "iPhone 14",
                    "price_cents": 1000,
                    "currency": "EUR",
                    "available": 11,
                    "is_active": True,
                },
                {
                    "sku": "IPHONE-14",
                    "title": "iPhone 14 Duplicate",
                    "price_cents": 1100,
                    "currency": "EUR",
                    "available": 5,
                    "is_active": True,
                }
            ]
        }

        url = reverse("fetcher-import")

        response = self.client.post(
            url,
            data=sku_idempotency_payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response_data = response.json()

        self.assertEqual(
            response_data["error"],
            "Invalid import payload.",
        )

        self.assertIn("items", response_data["details"])

    @patch("app.api.v1.fetcher.views.FetcherImportService.execute")
    def test_import_endpoint_returns_409_when_import_in_progress(self, execute_mock):
        execute_mock.side_effect = FetcherImportInProgressError(
            "Import already running for source=wildberries"
        )

        url = reverse("fetcher-import")

        response = self.client.post(
            url,
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(response.json()["success"])
        self.assertEqual(
            response.json()["error"],
            "Import already running for source=wildberries",
        )

    def test_import_endpoint_requires_api_key(self):
        response = self.client.post(
            reverse("fetcher-import"),
            data=self.payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_import_endpoint_rejects_invalid_api_key(self):
        response = self.client.post(
            reverse("fetcher-import"),
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="wrong-key",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_import_endpoint_accepts_valid_api_key(self):
        response = self.client.post(
            reverse("fetcher-import"),
            data=self.payload,
            format="json",
            HTTP_X_FETCHER_API_KEY="test-fetcher-key",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        response_data = response.json()

        self.assertTrue(response_data["success"])
        self.assertEqual(response_data["status"], "imported")
