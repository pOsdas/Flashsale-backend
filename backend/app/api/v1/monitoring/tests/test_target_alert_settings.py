from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from app.api.v1.monitoring.models import (
    AlertRule,
    AlertType,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
)
from app.api.v1.monitoring.services.alert_rule_constants import (
    MAX_ALERT_RULE_COOLDOWN_MINUTES,
    SUPPORTED_TARGET_ALERT_TYPES,
)


class MonitoringTargetAlertSettingsTestDataMixin:
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

    @classmethod
    def build_rules_payload(
        cls,
        *,
        overrides: dict[str, dict] | None = None,
    ) -> dict:
        rules = [
            {
                "alert_type": AlertType.PRICE_DROPPED,
                "threshold_percent": "5.00",
                "threshold_absolute": None,
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.PRICE_INCREASED,
                "threshold_percent": "5.00",
                "threshold_absolute": None,
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.BECAME_AVAILABLE,
                "threshold_percent": None,
                "threshold_absolute": None,
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.BECAME_UNAVAILABLE,
                "threshold_percent": None,
                "threshold_absolute": None,
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.RATING_CHANGED,
                "threshold_percent": None,
                "threshold_absolute": "0.10",
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.REVIEWS_COUNT_CHANGED,
                "threshold_percent": None,
                "threshold_absolute": "10.00",
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
            {
                "alert_type": AlertType.TITLE_CHANGED,
                "threshold_percent": None,
                "threshold_absolute": None,
                "cooldown_minutes": 360,
                "is_enabled": True,
            },
        ]

        overrides = overrides or {}

        for rule in rules:
            alert_type = rule["alert_type"]

            if alert_type in overrides:
                rule.update(overrides[alert_type])

        return {
            "rules": rules,
        }


class MonitoringTargetAlertSettingsAPITests(
    MonitoringTargetAlertSettingsTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.owner = self.create_user(
            "alert-settings-owner"
        )
        self.other_user = self.create_user(
            "alert-settings-other"
        )

        self.target = self.create_target(
            user=self.owner,
            external_id="123456",
        )

        self.url = (
            f"/api/v1/monitoring/targets/"
            f"{self.target.id}/alert-settings/"
        )

    def test_get_alert_settings_requires_authentication(
        self,
    ):
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

    def test_put_alert_settings_requires_authentication(
        self,
    ):
        response = self.client.put(
            self.url,
            data=self.build_rules_payload(),
            format="json",
        )

        self.assertIn(
            response.status_code,
            (
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ),
        )

    def test_get_returns_all_default_alert_settings(
        self,
    ):
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
            response.data["target_id"],
            str(self.target.id),
        )
        self.assertEqual(
            len(response.data["rules"]),
            len(SUPPORTED_TARGET_ALERT_TYPES),
        )

        returned_types = [
            rule["alert_type"]
            for rule in response.data["rules"]
        ]

        expected_types = [
            str(alert_type)
            for alert_type in SUPPORTED_TARGET_ALERT_TYPES
        ]

        self.assertEqual(
            returned_types,
            expected_types,
        )

        rules_by_type = {
            rule["alert_type"]: rule
            for rule in response.data["rules"]
        }

        for rule in response.data["rules"]:
            self.assertEqual(
                rule["source"],
                "default",
            )
            self.assertFalse(
                rule["is_custom"],
            )
            self.assertTrue(
                rule["is_enabled"],
            )

        price_dropped_rule = rules_by_type[
            AlertType.PRICE_DROPPED
        ]

        self.assertEqual(
            price_dropped_rule["threshold_percent"],
            "5.00",
        )
        self.assertIsNone(
            price_dropped_rule["threshold_absolute"],
        )
        self.assertEqual(
            price_dropped_rule["cooldown_minutes"],
            360,
        )

        rating_rule = rules_by_type[
            AlertType.RATING_CHANGED
        ]

        self.assertIsNone(
            rating_rule["threshold_percent"],
        )
        self.assertEqual(
            rating_rule["threshold_absolute"],
            "0.10",
        )

        reviews_rule = rules_by_type[
            AlertType.REVIEWS_COUNT_CHANGED
        ]

        self.assertEqual(
            reviews_rule["threshold_absolute"],
            "10.00",
        )

        self.assertFalse(
            AlertRule.objects.exists(),
        )

    def test_get_uses_global_rule_when_target_rule_is_missing(
        self,
    ):
        AlertRule.objects.create(
            user=self.owner,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("3.00"),
            threshold_absolute=Decimal("100.00"),
            cooldown_minutes=120,
            is_enabled=False,
        )

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

        rules_by_type = {
            rule["alert_type"]: rule
            for rule in response.data["rules"]
        }

        price_rule = rules_by_type[
            AlertType.PRICE_DROPPED
        ]

        self.assertEqual(
            price_rule["source"],
            "global",
        )
        self.assertTrue(
            price_rule["is_custom"],
        )
        self.assertFalse(
            price_rule["is_enabled"],
        )
        self.assertEqual(
            price_rule["threshold_percent"],
            "3.00",
        )
        self.assertEqual(
            price_rule["threshold_absolute"],
            "100.00",
        )
        self.assertEqual(
            price_rule["cooldown_minutes"],
            120,
        )

        other_rule = rules_by_type[
            AlertType.PRICE_INCREASED
        ]

        self.assertEqual(
            other_rule["source"],
            "default",
        )

    def test_get_target_rule_has_priority_over_global_rule(
        self,
    ):
        AlertRule.objects.create(
            user=self.owner,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("10.00"),
            cooldown_minutes=500,
            is_enabled=False,
        )
        AlertRule.objects.create(
            user=self.owner,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("2.00"),
            cooldown_minutes=30,
            is_enabled=True,
        )

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

        rules_by_type = {
            rule["alert_type"]: rule
            for rule in response.data["rules"]
        }

        price_rule = rules_by_type[
            AlertType.PRICE_DROPPED
        ]

        self.assertEqual(
            price_rule["source"],
            "target",
        )
        self.assertTrue(
            price_rule["is_custom"],
        )
        self.assertTrue(
            price_rule["is_enabled"],
        )
        self.assertEqual(
            price_rule["threshold_percent"],
            "2.00",
        )
        self.assertEqual(
            price_rule["cooldown_minutes"],
            30,
        )

    def test_foreign_user_cannot_get_alert_settings(
        self,
    ):
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

    def test_owner_can_replace_all_target_alert_settings(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "2.00",
                    "threshold_absolute": "100.00",
                    "cooldown_minutes": 60,
                    "is_enabled": True,
                },
                AlertType.PRICE_INCREASED: {
                    "threshold_percent": "7.00",
                    "threshold_absolute": None,
                    "cooldown_minutes": 120,
                    "is_enabled": False,
                },
                AlertType.RATING_CHANGED: {
                    "threshold_percent": None,
                    "threshold_absolute": "0.20",
                    "cooldown_minutes": 180,
                    "is_enabled": False,
                },
                AlertType.TITLE_CHANGED: {
                    "threshold_percent": None,
                    "threshold_absolute": None,
                    "cooldown_minutes": 0,
                    "is_enabled": False,
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["target_id"],
            str(self.target.id),
        )
        self.assertEqual(
            len(response.data["rules"]),
            len(SUPPORTED_TARGET_ALERT_TYPES),
        )
        self.assertEqual(
            AlertRule.objects.filter(
                target=self.target,
            ).count(),
            len(SUPPORTED_TARGET_ALERT_TYPES),
        )

        for rule_data in response.data["rules"]:
            self.assertEqual(
                rule_data["source"],
                "target",
            )
            self.assertTrue(
                rule_data["is_custom"],
            )

        price_dropped_rule = AlertRule.objects.get(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertEqual(
            price_dropped_rule.user,
            self.owner,
        )
        self.assertEqual(
            price_dropped_rule.threshold_percent,
            Decimal("2.00"),
        )
        self.assertEqual(
            price_dropped_rule.threshold_absolute,
            Decimal("100.00"),
        )
        self.assertEqual(
            price_dropped_rule.cooldown_minutes,
            60,
        )
        self.assertTrue(
            price_dropped_rule.is_enabled,
        )

        price_increased_rule = AlertRule.objects.get(
            target=self.target,
            alert_type=AlertType.PRICE_INCREASED,
        )

        self.assertFalse(
            price_increased_rule.is_enabled,
        )
        self.assertEqual(
            price_increased_rule.threshold_percent,
            Decimal("7.00"),
        )

        title_rule = AlertRule.objects.get(
            target=self.target,
            alert_type=AlertType.TITLE_CHANGED,
        )

        self.assertEqual(
            title_rule.cooldown_minutes,
            0,
        )
        self.assertFalse(
            title_rule.is_enabled,
        )

    def test_repeated_put_updates_rules_without_duplicates(
        self,
    ):
        first_payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "2.00",
                    "cooldown_minutes": 60,
                    "is_enabled": True,
                },
            }
        )

        second_payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "8.00",
                    "threshold_absolute": "500.00",
                    "cooldown_minutes": 720,
                    "is_enabled": False,
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        first_response = self.client.put(
            self.url,
            data=first_payload,
            format="json",
        )
        second_response = self.client.put(
            self.url,
            data=second_payload,
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
        self.assertEqual(
            AlertRule.objects.filter(
                target=self.target,
            ).count(),
            len(SUPPORTED_TARGET_ALERT_TYPES),
        )

        price_rule = AlertRule.objects.get(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertEqual(
            price_rule.threshold_percent,
            Decimal("8.00"),
        )
        self.assertEqual(
            price_rule.threshold_absolute,
            Decimal("500.00"),
        )
        self.assertEqual(
            price_rule.cooldown_minutes,
            720,
        )
        self.assertFalse(
            price_rule.is_enabled,
        )

    def test_put_does_not_modify_global_rules(
        self,
    ):
        global_rule = AlertRule.objects.create(
            user=self.owner,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("15.00"),
            threshold_absolute=Decimal("1000.00"),
            cooldown_minutes=900,
            is_enabled=False,
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=self.build_rules_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        global_rule.refresh_from_db()

        self.assertEqual(
            global_rule.threshold_percent,
            Decimal("15.00"),
        )
        self.assertEqual(
            global_rule.threshold_absolute,
            Decimal("1000.00"),
        )
        self.assertEqual(
            global_rule.cooldown_minutes,
            900,
        )
        self.assertFalse(
            global_rule.is_enabled,
        )

    def test_foreign_user_cannot_replace_alert_settings(
        self,
    ):
        self.client.force_authenticate(
            user=self.other_user,
        )

        response = self.client.put(
            self.url,
            data=self.build_rules_payload(),
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
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_missing_alert_type(
        self,
    ):
        payload = self.build_rules_payload()
        payload["rules"] = payload["rules"][:-1]

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_duplicate_alert_type(
        self,
    ):
        payload = self.build_rules_payload()

        payload["rules"][-1]["alert_type"] = (
            AlertType.PRICE_DROPPED
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_unsupported_alert_type(
        self,
    ):
        payload = self.build_rules_payload()

        payload["rules"][0]["alert_type"] = (
            AlertType.PRICE_CHANGED
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_thresholds_for_non_numeric_alert(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.BECAME_AVAILABLE: {
                    "threshold_percent": "5.00",
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_negative_threshold(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "-1.00",
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_negative_cooldown(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "cooldown_minutes": -1,
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_put_rejects_excessive_cooldown(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "cooldown_minutes": (
                        MAX_ALERT_RULE_COOLDOWN_MINUTES + 1
                    ),
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertFalse(
            AlertRule.objects.filter(
                target=self.target,
            ).exists(),
        )

    def test_invalid_put_does_not_change_existing_rules(
        self,
    ):
        initial_payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "2.00",
                    "cooldown_minutes": 60,
                    "is_enabled": True,
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        initial_response = self.client.put(
            self.url,
            data=initial_payload,
            format="json",
        )

        self.assertEqual(
            initial_response.status_code,
            status.HTTP_200_OK,
        )

        invalid_payload = self.build_rules_payload()
        invalid_payload["rules"] = (
            invalid_payload["rules"][:-1]
        )

        invalid_response = self.client.put(
            self.url,
            data=invalid_payload,
            format="json",
        )

        self.assertEqual(
            invalid_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            AlertRule.objects.filter(
                target=self.target,
            ).count(),
            len(SUPPORTED_TARGET_ALERT_TYPES),
        )

        price_rule = AlertRule.objects.get(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertEqual(
            price_rule.threshold_percent,
            Decimal("2.00"),
        )
        self.assertEqual(
            price_rule.cooldown_minutes,
            60,
        )
        self.assertTrue(
            price_rule.is_enabled,
        )

    def test_get_returns_saved_target_settings_after_put(
        self,
    ):
        payload = self.build_rules_payload(
            overrides={
                AlertType.PRICE_DROPPED: {
                    "threshold_percent": "1.50",
                    "threshold_absolute": "50.00",
                    "cooldown_minutes": 15,
                    "is_enabled": True,
                },
                AlertType.BECAME_UNAVAILABLE: {
                    "cooldown_minutes": 0,
                    "is_enabled": False,
                },
            }
        )

        self.client.force_authenticate(
            user=self.owner,
        )

        put_response = self.client.put(
            self.url,
            data=payload,
            format="json",
        )
        get_response = self.client.get(
            self.url,
        )

        self.assertEqual(
            put_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            get_response.status_code,
            status.HTTP_200_OK,
        )

        rules_by_type = {
            rule["alert_type"]: rule
            for rule in get_response.data["rules"]
        }

        price_rule = rules_by_type[
            AlertType.PRICE_DROPPED
        ]

        self.assertEqual(
            price_rule["threshold_percent"],
            "1.50",
        )
        self.assertEqual(
            price_rule["threshold_absolute"],
            "50.00",
        )
        self.assertEqual(
            price_rule["cooldown_minutes"],
            15,
        )
        self.assertTrue(
            price_rule["is_enabled"],
        )
        self.assertEqual(
            price_rule["source"],
            "target",
        )

        availability_rule = rules_by_type[
            AlertType.BECAME_UNAVAILABLE
        ]

        self.assertEqual(
            availability_rule["cooldown_minutes"],
            0,
        )
        self.assertFalse(
            availability_rule["is_enabled"],
        )
        self.assertEqual(
            availability_rule["source"],
            "target",
        )
