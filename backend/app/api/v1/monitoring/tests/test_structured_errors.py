from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.monitoring.models import (
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    ProductSnapshot,
    SnapshotParseStatus,
    SnapshotSource,
)
from app.api.v1.monitoring.services.product_preview import (
    ProductPreviewData,
    ProductPreviewError,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetCheckBusyError,
    MonitoringTargetCheckError,
)


class StructuredErrorTestDataMixin:
    password = "StrongTestPassword123!"

    @classmethod
    def create_user(cls, label: str):
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD

        if username_field == "email":
            identifier = f"{label}@example.com"
        else:
            identifier = label

        return user_model.objects.create_user(
            **{
                username_field: identifier,
                "password": cls.password,
            }
        )

    @staticmethod
    def create_target(
        *,
        user,
        external_id: str = "123456",
    ) -> MonitoringTarget:
        return MonitoringTarget.objects.create(
            user=user,
            marketplace=Marketplace.WILDBERRIES,
            role=MonitoringTargetRole.COMPETITOR,
            url=(
                "https://www.wildberries.ru/catalog/"
                f"{external_id}/detail.aspx"
            ),
            external_id=external_id,
            title="Test product",
            seller_name="Test seller",
            brand="Test brand",
            check_interval_minutes=60,
        )

    @staticmethod
    def create_snapshot(
        *,
        target: MonitoringTarget,
    ) -> ProductSnapshot:
        return ProductSnapshot.objects.create(
            target=target,
            parse_status=SnapshotParseStatus.SUCCESS,
            source=SnapshotSource.PARSER,
            price=Decimal("1499.00"),
            old_price=Decimal("1999.00"),
            currency="RUB",
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=125,
            title="Test product",
            seller_name="Test seller",
            brand="Test brand",
            raw_data={
                "source": "test",
            },
        )

    def assert_target_error(
        self,
        response,
        *,
        status_code: int,
        error_code: str,
        target_id,
    ) -> None:
        self.assertEqual(
            response.status_code,
            status_code,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            error_code,
        )
        self.assertIsInstance(
            response.data["error"],
            str,
        )
        self.assertEqual(
            response.data["details"]["target_id"],
            str(target_id),
        )


class MonitoringStructuredErrorAPITests(
    StructuredErrorTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "structured-error-owner"
        )
        self.other_user = self.create_user(
            "structured-error-other"
        )
        self.target = self.create_target(
            user=self.owner,
        )
        self.snapshot = self.create_snapshot(
            target=self.target,
        )

    def test_get_foreign_target_returns_structured_404(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.get(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/"
            ),
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=self.target.id,
        )

    def test_patch_missing_target_returns_structured_404(
        self,
    ):
        target_id = uuid4()

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            f"/api/v1/monitoring/targets/{target_id}/",
            data={
                "role": MonitoringTargetRole.OWN,
            },
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=target_id,
        )

    def test_pause_foreign_target_returns_structured_404(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/pause/"
            ),
            data={},
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=self.target.id,
        )

    def test_resume_foreign_target_returns_structured_404(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/resume/"
            ),
            data={},
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=self.target.id,
        )

    def test_check_now_foreign_target_returns_structured_404(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/check-now/"
            ),
            data={},
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=self.target.id,
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_busy_returns_structured_409(
        self,
        mock_check_monitoring_target_now,
    ):
        mock_check_monitoring_target_now.side_effect = (
            MonitoringTargetCheckBusyError(
                "Product cache refresh is already in progress."
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/check-now/"
            ),
            data={},
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_409_CONFLICT,
            error_code="refresh_busy",
            target_id=self.target.id,
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_failure_returns_structured_502(
        self,
        mock_check_monitoring_target_now,
    ):
        mock_check_monitoring_target_now.side_effect = (
            MonitoringTargetCheckError(
                "Marketplace request failed."
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/check-now/"
            ),
            data={},
            format="json",
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="check_failed",
            target_id=self.target.id,
        )

    def test_alert_settings_foreign_target_returns_structured_404(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.get(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/alert-settings/"
            ),
        )

        self.assert_target_error(
            response,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="target_not_found",
            target_id=self.target.id,
        )

    @patch(
        "app.api.v1.monitoring.views."
        "ProductPreviewService"
    )
    def test_product_preview_error_returns_structured_400(
        self,
        mock_product_preview_service_class,
    ):
        marketplace = Marketplace.WILDBERRIES
        url = (
            "https://www.wildberries.ru/catalog/"
            "123456/detail.aspx"
        )

        mock_product_preview_service = (
            mock_product_preview_service_class.return_value
        )
        mock_product_preview_service.preview_product.side_effect = (
            ProductPreviewError(
                "Product could not be parsed."
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            "/api/v1/monitoring/products/preview/",
            data={
                "marketplace": marketplace,
                "url": url,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "product_preview_failed",
        )
        self.assertEqual(
            response.data["details"]["marketplace"],
            marketplace,
        )
        self.assertEqual(
            response.data["details"]["url"],
            url,
        )

    def test_serializer_error_still_uses_validation_error(
        self,
    ):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            "/api/v1/monitoring/products/preview/",
            data={
                "marketplace": Marketplace.WILDBERRIES,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "validation_error",
        )
        self.assertIn(
            "url",
            response.data["details"],
        )

    def test_successful_target_response_is_not_error_wrapped(
        self,
    ):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.get(
            (
                f"/api/v1/monitoring/targets/"
                f"{self.target.id}/"
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            str(self.target.id),
        )
        self.assertNotIn(
            "error_code",
            response.data,
        )
        self.assertNotIn(
            "details",
            response.data,
        )

    @patch(
        "app.api.v1.monitoring.views."
        "ProductPreviewService"
    )
    def test_successful_preview_response_is_not_error_wrapped(
        self,
        mock_product_preview_service_class,
    ):
        marketplace = Marketplace.WILDBERRIES
        url = (
            "https://www.wildberries.ru/catalog/"
            "123456/detail.aspx"
        )

        mock_product_preview_service = (
            mock_product_preview_service_class.return_value
        )
        mock_product_preview_service.preview_product.return_value = (
            ProductPreviewData(
                external_id="123456",
                title="Test product",
                seller_name="Test seller",
                brand="Test brand",
                price=1499,
                old_price=1999,
                currency="RUB",
                is_available=True,
                rating=4.8,
                reviews_count=125,
                raw_data={
                    "source": "test",
                },
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            "/api/v1/monitoring/products/preview/",
            data={
                "marketplace": marketplace,
                "url": url,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            response.data["success"],
        )
        self.assertIn(
            "product",
            response.data,
        )
        self.assertNotIn(
            "error_code",
            response.data,
        )
        self.assertNotIn(
            "details",
            response.data,
        )
