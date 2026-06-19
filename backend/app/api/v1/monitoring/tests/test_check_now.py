from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
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
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetCheckBusyError,
    MonitoringTargetCheckError,
    MonitoringTargetCheckResult,
    MonitoringTargetNotFoundError,
    check_monitoring_target_now,
    get_monitoring_target_for_user,
)


class MonitoringTestDataMixin:
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
        price: Decimal = Decimal("1499.00"),
    ) -> ProductSnapshot:
        return ProductSnapshot.objects.create(
            target=target,
            parse_status=SnapshotParseStatus.SUCCESS,
            source=SnapshotSource.PARSER,
            price=price,
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


class MonitoringTargetCheckNowAPITests(
    MonitoringTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.owner = self.create_user("check-now-owner")
        self.other_user = self.create_user("check-now-other")

        self.target = self.create_target(
            user=self.owner,
            external_id="123456",
        )
        self.snapshot = self.create_snapshot(
            target=self.target,
        )

        self.url = (
            f"/api/v1/monitoring/targets/"
            f"{self.target.id}/check-now/"
        )

    def test_check_now_requires_authentication(self):
        response = self.client.post(
            self.url,
            data={},
            format="json",
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_returns_successful_response(
        self,
        mock_check_monitoring_target_now,
    ):
        mock_check_monitoring_target_now.return_value = (
            MonitoringTargetCheckResult(
                target=self.target,
                snapshot=self.snapshot,
                alerts_count=2,
                cache_source=SnapshotSource.PARSER,
                cache_is_stale=False,
                effective_cache_minutes=60,
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertTrue(
            response.data["success"],
        )
        self.assertEqual(
            response.data["target"]["id"],
            str(self.target.id),
        )
        self.assertEqual(
            response.data["snapshot"]["id"],
            str(self.snapshot.id),
        )
        self.assertEqual(
            response.data["snapshot"]["target_id"],
            str(self.target.id),
        )
        self.assertEqual(
            response.data["snapshot"]["source"],
            SnapshotSource.PARSER,
        )
        self.assertEqual(
            response.data["alerts_count"],
            2,
        )
        self.assertEqual(
            response.data["cache_source"],
            SnapshotSource.PARSER,
        )
        self.assertFalse(
            response.data["cache_is_stale"],
        )
        self.assertEqual(
            response.data["effective_cache_minutes"],
            60,
        )

        mock_check_monitoring_target_now.assert_called_once_with(
            user=self.owner,
            target_id=self.target.id,
        )

    def test_check_now_does_not_allow_access_to_foreign_target(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "target_not_found",
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_returns_404_when_target_not_found(
        self,
        mock_check_monitoring_target_now,
    ):
        mock_check_monitoring_target_now.side_effect = (
            MonitoringTargetNotFoundError(
                "Monitoring target was not found."
            )
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "target_not_found",
        )
        self.assertEqual(
            response.data["error"],
            "Monitoring target was not found.",
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_returns_409_when_refresh_is_busy(
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
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "refresh_busy",
        )

    @patch(
        "app.api.v1.monitoring.views."
        "check_monitoring_target_now"
    )
    def test_check_now_returns_502_when_check_fails(
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
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_502_BAD_GATEWAY,
        )
        self.assertFalse(
            response.data["success"],
        )
        self.assertEqual(
            response.data["error_code"],
            "check_failed",
        )
        self.assertEqual(
            response.data["error"],
            "Marketplace request failed.",
        )


class MonitoringTargetCheckNowServiceTests(
    MonitoringTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "check-now-service-owner"
        )
        self.other_user = self.create_user(
            "check-now-service-other"
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="654321",
        )
        self.snapshot = self.create_snapshot(
            target=self.target,
            price=Decimal("2499.00"),
        )

    def test_get_monitoring_target_returns_owned_target(
        self,
    ):
        result = get_monitoring_target_for_user(
            user=self.owner,
            target_id=self.target.id,
        )

        self.assertEqual(
            result.id,
            self.target.id,
        )
        self.assertEqual(
            result.user_id,
            self.owner.id,
        )

    def test_get_monitoring_target_hides_foreign_target(
        self,
    ):
        with self.assertRaises(
            MonitoringTargetNotFoundError
        ):
            get_monitoring_target_for_user(
                user=self.other_user,
                target_id=self.target.id,
            )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "MonitoringScanner"
    )
    def test_check_now_uses_forced_cache_refresh(
        self,
        mock_scanner_class,
    ):
        mock_scanner = mock_scanner_class.return_value

        mock_scanner.process_target.return_value = (
            SimpleNamespace(
                success=True,
                snapshot=self.snapshot,
                alerts_count=1,
                cache_source=SnapshotSource.PARSER,
                cache_is_stale=False,
                effective_cache_minutes=60,
                error="",
                busy=False,
            )
        )

        targets_count_before = (
            MonitoringTarget.objects.count()
        )

        result = check_monitoring_target_now(
            user=self.owner,
            target_id=self.target.id,
        )

        targets_count_after = (
            MonitoringTarget.objects.count()
        )

        self.assertEqual(
            targets_count_after,
            targets_count_before,
        )
        self.assertEqual(
            result.target.id,
            self.target.id,
        )
        self.assertEqual(
            result.snapshot.id,
            self.snapshot.id,
        )
        self.assertEqual(
            result.alerts_count,
            1,
        )
        self.assertEqual(
            result.cache_source,
            SnapshotSource.PARSER,
        )

        mock_scanner.process_target.assert_called_once_with(
            target=self.target,
            force_refresh=True,
            postpone_on_busy=False,
            trigger="manual_check",
        )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "MonitoringScanner"
    )
    def test_check_now_raises_busy_error(
        self,
        mock_scanner_class,
    ):
        mock_scanner = mock_scanner_class.return_value

        mock_scanner.process_target.return_value = (
            SimpleNamespace(
                success=False,
                snapshot=None,
                alerts_count=0,
                cache_source="",
                cache_is_stale=False,
                effective_cache_minutes=None,
                error=(
                    "Product cache refresh is already "
                    "in progress."
                ),
                busy=True,
            )
        )

        with self.assertRaises(
            MonitoringTargetCheckBusyError
        ):
            check_monitoring_target_now(
                user=self.owner,
                target_id=self.target.id,
            )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "MonitoringScanner"
    )
    def test_check_now_raises_check_error(
        self,
        mock_scanner_class,
    ):
        mock_scanner = mock_scanner_class.return_value

        mock_scanner.process_target.return_value = (
            SimpleNamespace(
                success=False,
                snapshot=self.snapshot,
                alerts_count=0,
                cache_source="",
                cache_is_stale=False,
                effective_cache_minutes=None,
                error="Marketplace request failed.",
                busy=False,
            )
        )

        with self.assertRaises(
            MonitoringTargetCheckError
        ):
            check_monitoring_target_now(
                user=self.owner,
                target_id=self.target.id,
            )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "MonitoringScanner"
    )
    def test_check_now_requires_created_snapshot(
        self,
        mock_scanner_class,
    ):
        mock_scanner = mock_scanner_class.return_value

        mock_scanner.process_target.return_value = (
            SimpleNamespace(
                success=True,
                snapshot=None,
                alerts_count=0,
                cache_source=SnapshotSource.PARSER,
                cache_is_stale=False,
                effective_cache_minutes=60,
                error="",
                busy=False,
            )
        )

        with self.assertRaisesRegex(
            MonitoringTargetCheckError,
            "did not create a snapshot",
        ):
            check_monitoring_target_now(
                user=self.owner,
                target_id=self.target.id,
            )

    @patch(
        "app.api.v1.monitoring.services.target_service."
        "MonitoringScanner"
    )
    def test_check_now_requires_cache_metadata(
        self,
        mock_scanner_class,
    ):
        mock_scanner = mock_scanner_class.return_value

        mock_scanner.process_target.return_value = (
            SimpleNamespace(
                success=True,
                snapshot=self.snapshot,
                alerts_count=0,
                cache_source=SnapshotSource.PARSER,
                cache_is_stale=False,
                effective_cache_minutes=None,
                error="",
                busy=False,
            )
        )

        with self.assertRaisesRegex(
            MonitoringTargetCheckError,
            "did not return cache metadata",
        ):
            check_monitoring_target_now(
                user=self.owner,
                target_id=self.target.id,
            )
