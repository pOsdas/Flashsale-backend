from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from app.api.v1.monitoring.models import SnapshotSource
from app.api.v1.monitoring.services.product_cache import (
    ProductCacheResult,
    ProductCacheService,
)


class ProductCacheCachedLookupTests(SimpleTestCase):
    def test_returns_fresh_cache_without_using_fetcher(self) -> None:
        fetcher_client = Mock()
        service = ProductCacheService(
            fetcher_client=fetcher_client,
        )
        cache_entry = SimpleNamespace(
            external_id="123",
        )
        parsed_at = timezone.now()
        cached_result = ProductCacheResult(
            product=SimpleNamespace(raw_data={}),
            source=SnapshotSource.CACHE,
            is_stale=False,
            parsed_at=parsed_at,
            expires_at=parsed_at + timedelta(minutes=60),
            effective_cache_minutes=60,
        )

        with patch.object(
            service,
            "_get_cache_entry",
            return_value=cache_entry,
        ) as get_cache_entry_mock, patch.object(
            service,
            "calculate_effective_cache_minutes",
            return_value=60,
        ), patch.object(
            service,
            "_build_fresh_cache_result_if_possible",
            return_value=cached_result,
        ):
            result = service.get_cached_product_by_identity(
                marketplace="wb",
                url=(
                    "https://www.wildberries.ru/"
                    "catalog/123/detail.aspx"
                ),
                external_id="123",
                fallback_interval_minutes=60,
            )

        self.assertIs(result, cached_result)
        get_cache_entry_mock.assert_called_once()
        fetcher_client.fetch_product.assert_not_called()
        fetcher_client.fetch_target.assert_not_called()
