from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.monitoring.models import (
    Alert,
    AlertRule,
    AlertType,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    ProductSnapshot,
    SnapshotParseStatus,
    SnapshotSource,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetNotFoundError,
    MonitoringTargetUpdateError,
    delete_monitoring_target,
    update_monitoring_target,
)


class MonitoringTargetTestDataMixin:
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
        role: str = MonitoringTargetRole.COMPETITOR,
        check_interval_minutes: int = 60,
    ) -> MonitoringTarget:
        return MonitoringTarget.objects.create(
            user=user,
            marketplace=Marketplace.WILDBERRIES,
            role=role,
            url=(
                "https://www.wildberries.ru/catalog/"
                f"{external_id}/detail.aspx"
            ),
            external_id=external_id,
            title="Test product",
            seller_name="Test seller",
            brand="Test brand",
            check_interval_minutes=check_interval_minutes,
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


class MonitoringTargetDetailAPITests(
    MonitoringTargetTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "target-detail-owner"
        )
        self.other_user = self.create_user(
            "target-detail-other"
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="123456",
        )
        self.snapshot = self.create_snapshot(
            target=self.target,
        )

        self.url = (
            f"/api/v1/monitoring/targets/"
            f"{self.target.id}/"
        )

    def test_get_target_requires_authentication(self):
        response = self.client.get(
            self.url,
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_patch_target_requires_authentication(self):
        response = self.client.patch(
            self.url,
            data={
                "role": MonitoringTargetRole.OWN,
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_delete_target_requires_authentication(self):
        response = self.client.delete(
            self.url,
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_owner_can_get_target(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.get(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            str(self.target.id),
        )
        self.assertEqual(
            response.data["marketplace"],
            Marketplace.WILDBERRIES,
        )
        self.assertEqual(
            response.data["role"],
            MonitoringTargetRole.COMPETITOR,
        )
        self.assertEqual(
            response.data["external_id"],
            "123456",
        )
        self.assertEqual(
            response.data["latest_price"],
            "1499.00",
        )
        self.assertEqual(
            response.data["latest_rating"],
            "4.80",
        )
        self.assertEqual(
            response.data["latest_reviews_count"],
            125,
        )
        self.assertTrue(
            response.data["latest_is_available"],
        )

    def test_foreign_user_cannot_get_target(self):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.get(
            self.url,
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

    def test_owner_can_update_target_role(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "role": MonitoringTargetRole.OWN,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["role"],
            MonitoringTargetRole.OWN,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.OWN,
        )

    def test_owner_can_update_check_interval(self):
        checked_at = timezone.now()

        self.target.last_checked_at = checked_at
        self.target.save(
            update_fields=[
                "last_checked_at",
                "updated_at",
            ]
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "check_interval_minutes": 180,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["check_interval_minutes"],
            180,
        )

        self.target.refresh_from_db()

        expected_next_check_at = (
            checked_at + timedelta(minutes=180)
        )

        self.assertEqual(
            self.target.check_interval_minutes,
            180,
        )
        self.assertAlmostEqual(
            self.target.next_check_at,
            expected_next_check_at,
            delta=timedelta(seconds=1),
        )

    def test_interval_update_makes_overdue_target_due_now(self):
        checked_at = (
            timezone.now() - timedelta(hours=10)
        )
        request_started_at = timezone.now()

        self.target.last_checked_at = checked_at
        self.target.save(
            update_fields=[
                "last_checked_at",
                "updated_at",
            ]
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "check_interval_minutes": 60,
            },
            format="json",
        )

        request_finished_at = timezone.now()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.target.refresh_from_db()

        self.assertGreaterEqual(
            self.target.next_check_at,
            request_started_at,
        )
        self.assertLessEqual(
            self.target.next_check_at,
            request_finished_at,
        )

    def test_interval_update_without_previous_check_is_due_now(
        self,
    ):
        self.target.last_checked_at = None
        self.target.save(
            update_fields=[
                "last_checked_at",
                "updated_at",
            ]
        )

        request_started_at = timezone.now()

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "check_interval_minutes": 120,
            },
            format="json",
        )

        request_finished_at = timezone.now()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.target.refresh_from_db()

        self.assertGreaterEqual(
            self.target.next_check_at,
            request_started_at,
        )
        self.assertLessEqual(
            self.target.next_check_at,
            request_finished_at,
        )

    def test_owner_can_update_role_and_interval_together(
        self,
    ):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "role": MonitoringTargetRole.OWN,
                "check_interval_minutes": 360,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["role"],
            MonitoringTargetRole.OWN,
        )
        self.assertEqual(
            response.data["check_interval_minutes"],
            360,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.OWN,
        )
        self.assertEqual(
            self.target.check_interval_minutes,
            360,
        )

    def test_patch_rejects_interval_below_minimum(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "check_interval_minutes": 14,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "check_interval_minutes",
            response.data,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.check_interval_minutes,
            60,
        )

    def test_patch_rejects_interval_above_maximum(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "check_interval_minutes": 1441,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "check_interval_minutes",
            response.data,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.check_interval_minutes,
            60,
        )

    def test_patch_rejects_invalid_role(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "role": "invalid-role",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "role",
            response.data,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.COMPETITOR,
        )

    def test_patch_rejects_empty_body(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn(
            "non_field_errors",
            response.data,
        )

    def test_patch_does_not_allow_url_update(self):
        original_url = self.target.url

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.patch(
            self.url,
            data={
                "url": (
                    "https://www.wildberries.ru/catalog/"
                    "999999/detail.aspx"
                ),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.url,
            original_url,
        )

    def test_foreign_user_cannot_patch_target(self):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.patch(
            self.url,
            data={
                "role": MonitoringTargetRole.OWN,
            },
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

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.COMPETITOR,
        )

    def test_owner_can_delete_target_with_related_records(
        self,
    ):
        alert_rule = AlertRule.objects.create(
            user=self.owner,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        alert = Alert.objects.create(
            user=self.owner,
            target=self.target,
            snapshot=self.snapshot,
            alert_type=AlertType.PRICE_DROPPED,
            title="Price dropped",
            message="The product price decreased.",
            old_value="1999.00",
            new_value="1499.00",
            dedup_key=(
                f"test-delete-target-{self.target.id}"
            ),
        )

        target_id = self.target.id
        snapshot_id = self.snapshot.id
        alert_id = alert.id
        alert_rule_id = alert_rule.id

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.delete(
            self.url,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertEqual(
            response.content,
            b"",
        )

        self.assertFalse(
            MonitoringTarget.objects.filter(
                id=target_id,
            ).exists()
        )
        self.assertFalse(
            ProductSnapshot.objects.filter(
                id=snapshot_id,
            ).exists()
        )
        self.assertFalse(
            Alert.objects.filter(
                id=alert_id,
            ).exists()
        )
        self.assertFalse(
            AlertRule.objects.filter(
                id=alert_rule_id,
            ).exists()
        )

    def test_foreign_user_cannot_delete_target(self):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.delete(
            self.url,
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

        self.assertTrue(
            MonitoringTarget.objects.filter(
                id=self.target.id,
            ).exists()
        )


class MonitoringTargetManagementServiceTests(
    MonitoringTargetTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "target-service-owner"
        )
        self.other_user = self.create_user(
            "target-service-other"
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="654321",
        )

    def test_update_monitoring_target_updates_role(self):
        result = update_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
            validated_data={
                "role": MonitoringTargetRole.OWN,
            },
        )

        self.assertEqual(
            result.role,
            MonitoringTargetRole.OWN,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.OWN,
        )

    def test_update_monitoring_target_recalculates_schedule(
        self,
    ):
        checked_at = timezone.now()

        self.target.last_checked_at = checked_at
        self.target.save(
            update_fields=[
                "last_checked_at",
                "updated_at",
            ]
        )

        result = update_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
            validated_data={
                "check_interval_minutes": 240,
            },
        )

        expected_next_check_at = (
            checked_at + timedelta(minutes=240)
        )

        self.assertEqual(
            result.check_interval_minutes,
            240,
        )
        self.assertAlmostEqual(
            result.next_check_at,
            expected_next_check_at,
            delta=timedelta(seconds=1),
        )

    def test_update_monitoring_target_rejects_empty_data(
        self,
    ):
        with self.assertRaisesRegex(
            MonitoringTargetUpdateError,
            "At least one field must be provided",
        ):
            update_monitoring_target(
                user=self.owner,
                target_id=self.target.id,
                validated_data={},
            )

    def test_update_monitoring_target_rejects_unsupported_fields(
        self,
    ):
        with self.assertRaisesRegex(
            MonitoringTargetUpdateError,
            "Unsupported monitoring target fields",
        ):
            update_monitoring_target(
                user=self.owner,
                target_id=self.target.id,
                validated_data={
                    "url": (
                        "https://www.wildberries.ru/catalog/"
                        "999999/detail.aspx"
                    ),
                },
            )

    def test_update_monitoring_target_rejects_invalid_interval(
        self,
    ):
        with self.assertRaisesRegex(
            MonitoringTargetUpdateError,
            "between 15 and 1440 minutes",
        ):
            update_monitoring_target(
                user=self.owner,
                target_id=self.target.id,
                validated_data={
                    "check_interval_minutes": 5,
                },
            )

    def test_update_monitoring_target_hides_foreign_target(
        self,
    ):
        with self.assertRaises(
            MonitoringTargetNotFoundError
        ):
            update_monitoring_target(
                user=self.other_user,
                target_id=self.target.id,
                validated_data={
                    "role": MonitoringTargetRole.OWN,
                },
            )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.role,
            MonitoringTargetRole.COMPETITOR,
        )

    def test_delete_monitoring_target_deletes_owned_target(
        self,
    ):
        target_id = self.target.id

        delete_monitoring_target(
            user=self.owner,
            target_id=target_id,
        )

        self.assertFalse(
            MonitoringTarget.objects.filter(
                id=target_id,
            ).exists()
        )

    def test_delete_monitoring_target_hides_foreign_target(
        self,
    ):
        with self.assertRaises(
            MonitoringTargetNotFoundError
        ):
            delete_monitoring_target(
                user=self.other_user,
                target_id=self.target.id,
            )

        self.assertTrue(
            MonitoringTarget.objects.filter(
                id=self.target.id,
            ).exists()
        )
