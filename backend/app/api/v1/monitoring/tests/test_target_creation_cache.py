from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from app.api.v1.monitoring.models import SnapshotSource
from app.api.v1.monitoring.services.product_cache import (
    ProductCacheResult,
)
from app.api.v1.monitoring.services.target_service import (
    create_monitoring_target,
)


class MonitoringTargetCreationCacheTests(SimpleTestCase):
    def setUp(self) -> None:
        self.user = SimpleNamespace(id=7)
        self.target = Mock()
        self.target.id = "target-id"
        self.target.marketplace = "wb"
        self.target.url = (
            "https://www.wildberries.ru/catalog/123/detail.aspx"
        )
        self.target.external_id = ""
        self.target.check_interval_minutes = 60
        self.product = SimpleNamespace(
            external_id="123",
            title="Товар",
            seller_name="Продавец",
            brand="Бренд",
            price=Decimal("1000.00"),
            old_price=Decimal("1200.00"),
            currency="RUB",
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=15,
            raw_data={"id": 123},
        )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "build_monitoring_fetcher_client"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "create_product_snapshot"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "ProductCacheService"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "resolve_monitoring_target"
    )
    def test_uses_preview_cache_without_fetching_again(
        self,
        resolve_target_mock,
        cache_service_class_mock,
        create_snapshot_mock,
        build_fetcher_mock,
    ) -> None:
        resolve_target_mock.return_value = SimpleNamespace(
            target=self.target,
            created=True,
        )
        parsed_at = timezone.now()
        cache_result = ProductCacheResult(
            product=self.product,
            source=SnapshotSource.CACHE,
            is_stale=False,
            parsed_at=parsed_at,
            expires_at=parsed_at + timedelta(minutes=60),
            effective_cache_minutes=60,
        )
        cache_service_class_mock.return_value\
            .get_cached_product_by_identity.return_value = cache_result

        result = create_monitoring_target(
            user=self.user,
            validated_data={
                "marketplace": "wb",
                "url": self.target.url,
                "external_id": "123",
                "check_interval_minutes": 60,
            },
        )

        self.assertIs(result, self.target)
        cache_service_class_mock.return_value\
            .get_cached_product_by_identity.assert_called_once_with(
                marketplace="wb",
                url=self.target.url,
                external_id="123",
                fallback_interval_minutes=60,
                allow_stale=True,
            )
        build_fetcher_mock.assert_not_called()
        create_snapshot_mock.assert_called_once_with(
            target=self.target,
            parse_status="success",
            source=SnapshotSource.CACHE,
            price=Decimal("1000.00"),
            old_price=Decimal("1200.00"),
            currency="RUB",
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=15,
            title="Товар",
            seller_name="Продавец",
            brand="Бренд",
            external_id="123",
            raw_data=cache_result.build_snapshot_raw_data(),
            error_message="",
            checked_at=parsed_at,
        )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "build_monitoring_fetcher_client"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "create_product_snapshot"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "ProductCacheService"
    )
    @patch(
        "app.api.v1.monitoring.services.target_service."
        "resolve_monitoring_target"
    )
    def test_fetches_only_when_preview_cache_is_missing(
        self,
        resolve_target_mock,
        cache_service_class_mock,
        create_snapshot_mock,
        build_fetcher_mock,
    ) -> None:
        resolve_target_mock.return_value = SimpleNamespace(
            target=self.target,
            created=True,
        )
        cache_service_class_mock.return_value\
            .get_cached_product_by_identity.return_value = None
        fetcher_client = build_fetcher_mock.return_value
        fetcher_client.fetch_target.return_value = self.product

        create_monitoring_target(
            user=self.user,
            validated_data={
                "marketplace": "wb",
                "url": self.target.url,
                "external_id": "123",
                "check_interval_minutes": 60,
            },
        )

        build_fetcher_mock.assert_called_once_with()
        fetcher_client.fetch_target.assert_called_once_with(
            target=self.target,
        )
        create_snapshot_mock.assert_called_once_with(
            target=self.target,
            parse_status="success",
            price=Decimal("1000.00"),
            old_price=Decimal("1200.00"),
            currency="RUB",
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=15,
            title="Товар",
            seller_name="Продавец",
            brand="Бренд",
            external_id="123",
            raw_data={"id": 123},
            error_message="",
        )
