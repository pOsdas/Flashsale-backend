from typing import Any

from django.db import transaction
from django.utils import timezone

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.payments.models import ProcessedWebhookEvent
from app.api.v1.common import create_outbox_event
from app.api.v1.common.locks import RedisLock, RedisLockAlreadyAcquiredError
from app.api.v1.fetcher.exceptions import (
    FetcherBatchAlreadyProcessedError,
    FetcherUpsertError,
    FetcherStockUpdateError,
    FetcherCurrencyNotSupportedError,
    FetcherImportInProgressError,
)


SUPPORTED_CURRENCIES = {"EUR"}


class FetcherImportService:
    def __init__(
            self,
            *,
            source: str,
            batch_id: str,
            items: list[dict[str, Any]],
    ):
        self.source = source
        self.batch_id = batch_id
        self.items = items

    def execute(self) -> dict:
        lock_key = f"fetcher_import:{self.source}"

        try:
            with RedisLock(key=lock_key, ttl=60):
                return self._execute_locked()
        except RedisLockAlreadyAcquiredError as e:
            raise FetcherImportInProgressError(
                f"Import already running for source={self.source}"
            ) from e

    def _execute_locked(self) -> dict:
        if self._is_batch_processed():
            raise FetcherBatchAlreadyProcessedError(
                f"Batch already processed: {self.batch_id}"
            )

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for item in self.items:
                is_created = self._upsert_product_and_stock(item)

                if is_created:
                    created_count += 1
                else:
                    updated_count += 1

            self._mark_batch_processed()

            create_outbox_event(
                topic="catalog.import.completed",
                payload={
                    "source": self.source,
                    "batch_id": self.batch_id,
                    "created": created_count,
                    "updated": updated_count,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        return {
            "created": created_count,
            "updated": updated_count,
        }

    def _is_batch_processed(self) -> bool:
        return ProcessedWebhookEvent.objects.filter(
            provider=self.source,
            event_id=self.batch_id,
        ).exists()

    def _mark_batch_processed(self) -> None:
        ProcessedWebhookEvent.objects.create(
            provider=self.source,
            event_id=self.batch_id,
            payload={"type": "fetcher_import"}
        )

    def _upsert_product_and_stock(self, item: dict[str, Any]) -> bool:
        sku = item["sku"]
        title = item["title"]
        price_cents = item["price_cents"]
        currency = item["currency"]
        available = item["available"]
        is_active = item["is_active"]

        if currency not in SUPPORTED_CURRENCIES:
            raise FetcherCurrencyNotSupportedError(f"Unsupported currency: {currency}")

        try:
            product, created = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "title": title,
                    "price_cents": price_cents,
                    "currency": currency,
                    "is_active": is_active,
                },
            )
        except Exception as e:
            raise FetcherUpsertError(f"Failed to upsert product: {sku}") from e

        try:
            Stock.objects.update_or_create(
                product=product,
                defaults={
                    "available": available,
                },
            )
        except Exception as e:
            raise FetcherStockUpdateError(f"Failed to update stock for {sku}") from e

        return created
