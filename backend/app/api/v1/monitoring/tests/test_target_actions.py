from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.monitoring.models import (
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    MonitoringTargetStatus,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetNotFoundError,
    pause_monitoring_target,
    resume_monitoring_target,
)


class MonitoringTargetActionTestDataMixin:
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
        status_value: str = MonitoringTargetStatus.ACTIVE,
        is_active: bool = True,
        last_error: str = "",
        next_check_at=None,
    ) -> MonitoringTarget:
        return MonitoringTarget.objects.create(
            user=user,
            marketplace=Marketplace.WILDBERRIES,
            role=MonitoringTargetRole.COMPETITOR,
            status=status_value,
            is_active=is_active,
            url=(
                "https://www.wildberries.ru/catalog/"
                f"{external_id}/detail.aspx"
            ),
            external_id=external_id,
            title="Test product",
            seller_name="Test seller",
            brand="Test brand",
            check_interval_minutes=60,
            next_check_at=next_check_at or timezone.now(),
            last_error=last_error,
        )


class MonitoringTargetActionAPITests(
    MonitoringTargetActionTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "target-action-owner"
        )
        self.other_user = self.create_user(
            "target-action-other"
        )

        self.future_next_check_at = (
            timezone.now() + timedelta(hours=2)
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="123456",
            next_check_at=self.future_next_check_at,
        )

        self.pause_url = (
            f"/api/v1/monitoring/targets/"
            f"{self.target.id}/pause/"
        )
        self.resume_url = (
            f"/api/v1/monitoring/targets/"
            f"{self.target.id}/resume/"
        )

    def test_pause_requires_authentication(self):
        response = self.client.post(
            self.pause_url,
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

    def test_resume_requires_authentication(self):
        response = self.client.post(
            self.resume_url,
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

    def test_owner_can_pause_active_target(self):
        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.pause_url,
            data={},
            format="json",
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
            response.data["status"],
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            response.data["is_active"],
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            self.target.is_active,
        )

    def test_pause_preserves_next_check_at(self):
        original_next_check_at = self.target.next_check_at

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.pause_url,
            data={},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )

    def test_repeated_pause_is_idempotent(self):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.last_error = "Previous marketplace error"
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "last_error",
                "updated_at",
            ]
        )

        original_next_check_at = self.target.next_check_at

        self.client.force_authenticate(
            user=self.owner,
        )

        first_response = self.client.post(
            self.pause_url,
            data={},
            format="json",
        )
        second_response = self.client.post(
            self.pause_url,
            data={},
            format="json",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )
        self.assertEqual(
            self.target.last_error,
            "Previous marketplace error",
        )

    def test_foreign_user_cannot_pause_target(self):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            self.pause_url,
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

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )

    def test_owner_can_resume_paused_target(self):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.last_error = "Previous marketplace error"
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "last_error",
                "updated_at",
            ]
        )

        request_started_at = timezone.now()

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.resume_url,
            data={},
            format="json",
        )

        request_finished_at = timezone.now()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["id"],
            str(self.target.id),
        )
        self.assertEqual(
            response.data["status"],
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            response.data["is_active"],
        )
        self.assertEqual(
            response.data["last_error"],
            "",
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.last_error,
            "",
        )
        self.assertGreaterEqual(
            self.target.next_check_at,
            request_started_at,
        )
        self.assertLessEqual(
            self.target.next_check_at,
            request_finished_at,
        )

    def test_owner_can_resume_failed_target(self):
        self.target.status = MonitoringTargetStatus.FAILED
        self.target.is_active = True
        self.target.last_error = "Parser request failed"
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "last_error",
                "updated_at",
            ]
        )

        request_started_at = timezone.now()

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.post(
            self.resume_url,
            data={},
            format="json",
        )

        request_finished_at = timezone.now()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["status"],
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            response.data["is_active"],
        )
        self.assertEqual(
            response.data["last_error"],
            "",
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.last_error,
            "",
        )
        self.assertGreaterEqual(
            self.target.next_check_at,
            request_started_at,
        )
        self.assertLessEqual(
            self.target.next_check_at,
            request_finished_at,
        )

    def test_repeated_resume_of_active_target_preserves_schedule(
        self,
    ):
        original_next_check_at = self.target.next_check_at

        self.client.force_authenticate(
            user=self.owner,
        )

        first_response = self.client.post(
            self.resume_url,
            data={},
            format="json",
        )
        second_response = self.client.post(
            self.resume_url,
            data={},
            format="json",
        )

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_200_OK,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )

    def test_foreign_user_cannot_resume_target(self):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "updated_at",
            ]
        )

        original_next_check_at = self.target.next_check_at

        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.post(
            self.resume_url,
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

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )


class MonitoringTargetActionServiceTests(
    MonitoringTargetActionTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "target-action-service-owner"
        )
        self.other_user = self.create_user(
            "target-action-service-other"
        )

        self.future_next_check_at = (
            timezone.now() + timedelta(hours=3)
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="654321",
            next_check_at=self.future_next_check_at,
        )

    def test_pause_monitoring_target_updates_state(self):
        result = pause_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )

        self.assertEqual(
            result.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            result.is_active,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            self.target.is_active,
        )

    def test_pause_monitoring_target_is_idempotent(self):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "updated_at",
            ]
        )

        original_next_check_at = self.target.next_check_at

        first_result = pause_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )
        second_result = pause_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )

        self.assertEqual(
            first_result.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertEqual(
            second_result.status,
            MonitoringTargetStatus.PAUSED,
        )

        self.target.refresh_from_db()

        self.assertFalse(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )

    def test_pause_monitoring_target_hides_foreign_target(
        self,
    ):
        with self.assertRaises(
            MonitoringTargetNotFoundError
        ):
            pause_monitoring_target(
                user=self.other_user,
                target_id=self.target.id,
            )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )

    def test_resume_monitoring_target_updates_state(self):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.last_error = "Temporary parser error"
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "last_error",
                "updated_at",
            ]
        )

        request_started_at = timezone.now()

        result = resume_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )

        request_finished_at = timezone.now()

        self.assertEqual(
            result.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            result.is_active,
        )
        self.assertEqual(
            result.last_error,
            "",
        )
        self.assertGreaterEqual(
            result.next_check_at,
            request_started_at,
        )
        self.assertLessEqual(
            result.next_check_at,
            request_finished_at,
        )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.last_error,
            "",
        )

    def test_resume_monitoring_target_restores_failed_target(
        self,
    ):
        self.target.status = MonitoringTargetStatus.FAILED
        self.target.is_active = True
        self.target.last_error = "Marketplace unavailable"
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "last_error",
                "updated_at",
            ]
        )

        result = resume_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )

        self.assertEqual(
            result.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertTrue(
            result.is_active,
        )
        self.assertEqual(
            result.last_error,
            "",
        )

    def test_resume_active_target_is_idempotent(self):
        original_next_check_at = self.target.next_check_at

        first_result = resume_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )
        second_result = resume_monitoring_target(
            user=self.owner,
            target_id=self.target.id,
        )

        self.assertEqual(
            first_result.status,
            MonitoringTargetStatus.ACTIVE,
        )
        self.assertEqual(
            second_result.status,
            MonitoringTargetStatus.ACTIVE,
        )

        self.target.refresh_from_db()

        self.assertTrue(
            self.target.is_active,
        )
        self.assertEqual(
            self.target.next_check_at,
            original_next_check_at,
        )

    def test_resume_monitoring_target_hides_foreign_target(
        self,
    ):
        self.target.status = MonitoringTargetStatus.PAUSED
        self.target.is_active = False
        self.target.save(
            update_fields=[
                "status",
                "is_active",
                "updated_at",
            ]
        )

        with self.assertRaises(
            MonitoringTargetNotFoundError
        ):
            resume_monitoring_target(
                user=self.other_user,
                target_id=self.target.id,
            )

        self.target.refresh_from_db()

        self.assertEqual(
            self.target.status,
            MonitoringTargetStatus.PAUSED,
        )
        self.assertFalse(
            self.target.is_active,
        )
