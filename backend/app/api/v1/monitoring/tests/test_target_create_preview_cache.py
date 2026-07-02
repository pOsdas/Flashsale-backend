from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.monitoring.models import (
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    ProductSnapshot,
    SnapshotSource,
)
from app.api.v1.monitoring.services.fetcher_client import (
    FetchedProductData,
)


class MonitoringTargetPreviewCacheAPITests(APITestCase):
    password = "StrongTestPassword123!"

    def setUp(self):
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD

        if username_field == "email":
            identifier = "preview-cache@example.com"
        else:
            identifier = "preview-cache-user"

        self.user = user_model.objects.create_user(
            **{
                username_field: identifier,
                "password": self.password,
            }
        )
        self.client.force_authenticate(user=self.user)

        self.preview_url = (
            "/api/v1/monitoring/products/preview/"
        )
        self.targets_url = (
            "/api/v1/monitoring/targets/"
        )

    def test_preview_then_create_reuses_cache_without_second_parser_call(
        self,
    ):
        preview_product = self._build_product(
            external_id="123456",
            title="Preview product",
        )
        cache_client = Mock()
        cache_client.fetch_product.return_value = (
            preview_product
        )

        preview_product_url = (
            "https://www.wildberries.ru/catalog/"
            "123456/detail.aspx?from=preview"
        )
        target_product_url = (
            "https://www.wildberries.ru/catalog/"
            "123456/detail.aspx"
        )

        with (
            patch(
                "app.api.v1.monitoring.services."
                "product_cache.RedisLock"
            ) as redis_lock_class,
            patch(
                "app.api.v1.monitoring.services."
                "product_cache.build_monitoring_fetcher_client",
                return_value=cache_client,
            ),
            patch(
                "app.api.v1.monitoring.services."
                "target_service.build_monitoring_fetcher_client"
            ) as target_fetcher_builder,
        ):
            redis_lock_class.return_value.__enter__.return_value = (
                None
            )
            redis_lock_class.return_value.__exit__.return_value = (
                False
            )

            preview_response = self.client.post(
                self.preview_url,
                data={
                    "marketplace": Marketplace.WILDBERRIES,
                    "url": preview_product_url,
                },
                format="json",
            )

            self.assertEqual(
                preview_response.status_code,
                status.HTTP_200_OK,
            )

            create_response = self.client.post(
                self.targets_url,
                data={
                    "marketplace": Marketplace.WILDBERRIES,
                    "role": MonitoringTargetRole.COMPETITOR,
                    "url": target_product_url,
                    "external_id": (
                        preview_response.data["product"][
                            "external_id"
                        ]
                    ),
                    "check_interval_minutes": 60,
                },
                format="json",
            )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )
        cache_client.fetch_product.assert_called_once()
        target_fetcher_builder.assert_not_called()

        target = MonitoringTarget.objects.get(
            user=self.user,
        )
        snapshot = ProductSnapshot.objects.get(
            target=target,
        )

        self.assertEqual(
            target.external_id,
            "123456",
        )
        self.assertEqual(
            snapshot.source,
            SnapshotSource.CACHE,
        )
        self.assertEqual(
            snapshot.title,
            "Preview product",
        )
        self.assertEqual(
            create_response.data["external_id"],
            "123456",
        )

    def test_mismatched_external_id_does_not_reuse_another_product_cache(
        self,
    ):
        preview_product = self._build_product(
            external_id="111111",
            title="Cached product",
        )
        fetched_target_product = self._build_product(
            external_id="222222",
            title="Requested product",
        )

        cache_client = Mock()
        cache_client.fetch_product.return_value = (
            preview_product
        )
        target_client = Mock()
        target_client.fetch_target.return_value = (
            fetched_target_product
        )

        cached_product_url = (
            "https://www.wildberries.ru/catalog/"
            "111111/detail.aspx"
        )
        requested_product_url = (
            "https://www.wildberries.ru/catalog/"
            "222222/detail.aspx"
        )

        with (
            patch(
                "app.api.v1.monitoring.services."
                "product_cache.RedisLock"
            ) as redis_lock_class,
            patch(
                "app.api.v1.monitoring.services."
                "product_cache.build_monitoring_fetcher_client",
                return_value=cache_client,
            ),
            patch(
                "app.api.v1.monitoring.services."
                "target_service.build_monitoring_fetcher_client",
                return_value=target_client,
            ),
        ):
            redis_lock_class.return_value.__enter__.return_value = (
                None
            )
            redis_lock_class.return_value.__exit__.return_value = (
                False
            )

            preview_response = self.client.post(
                self.preview_url,
                data={
                    "marketplace": Marketplace.WILDBERRIES,
                    "url": cached_product_url,
                },
                format="json",
            )

            self.assertEqual(
                preview_response.status_code,
                status.HTTP_200_OK,
            )

            create_response = self.client.post(
                self.targets_url,
                data={
                    "marketplace": Marketplace.WILDBERRIES,
                    "role": MonitoringTargetRole.COMPETITOR,
                    "url": requested_product_url,
                    "external_id": "111111",
                    "check_interval_minutes": 60,
                },
                format="json",
            )

        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
        )
        cache_client.fetch_product.assert_called_once()
        target_client.fetch_target.assert_called_once()

        target = MonitoringTarget.objects.get(
            user=self.user,
        )
        snapshot = ProductSnapshot.objects.get(
            target=target,
        )

        self.assertEqual(
            target.external_id,
            "222222",
        )
        self.assertEqual(
            snapshot.source,
            SnapshotSource.PARSER,
        )
        self.assertEqual(
            snapshot.title,
            "Requested product",
        )

    def test_create_without_preview_keeps_parser_fallback(
        self,
    ):
        fetched_product = self._build_product(
            external_id="333333",
            title="Directly fetched product",
        )
        cache_client = Mock()
        target_client = Mock()
        target_client.fetch_target.return_value = (
            fetched_product
        )

        with (
            patch(
                "app.api.v1.monitoring.services."
                "product_cache.build_monitoring_fetcher_client",
                return_value=cache_client,
            ),
            patch(
                "app.api.v1.monitoring.services."
                "target_service.build_monitoring_fetcher_client",
                return_value=target_client,
            ),
        ):
            response = self.client.post(
                self.targets_url,
                data={
                    "marketplace": Marketplace.WILDBERRIES,
                    "role": MonitoringTargetRole.COMPETITOR,
                    "url": (
                        "https://www.wildberries.ru/catalog/"
                        "333333/detail.aspx"
                    ),
                    "check_interval_minutes": 60,
                },
                format="json",
            )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        target_client.fetch_target.assert_called_once()

        target = MonitoringTarget.objects.get(
            user=self.user,
        )
        snapshot = ProductSnapshot.objects.get(
            target=target,
        )

        self.assertEqual(
            target.external_id,
            "333333",
        )
        self.assertEqual(
            snapshot.source,
            SnapshotSource.PARSER,
        )

    @staticmethod
    def _build_product(
        *,
        external_id: str,
        title: str,
    ) -> FetchedProductData:
        return FetchedProductData(
            external_id=external_id,
            title=title,
            seller_name="Test seller",
            brand="Test brand",
            price=Decimal("1499.00"),
            old_price=Decimal("1999.00"),
            currency="RUB",
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=125,
            raw_data={
                "source": "test",
                "external_id": external_id,
            },
        )
