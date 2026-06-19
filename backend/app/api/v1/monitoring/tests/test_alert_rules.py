from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

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
from app.api.v1.monitoring.services.alert_rule_service import (
    get_effective_alert_rule,
)
from app.api.v1.monitoring.services.alert_service import (
    create_alerts_for_snapshot,
)
from app.api.v1.orders.models import OutboxEvent


class AlertRuleTestDataMixin:
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
        checked_at,
        price: Decimal = Decimal("100.00"),
        rating: Decimal = Decimal("4.50"),
        reviews_count: int = 100,
        is_available: bool = True,
        title: str = "Test product",
    ) -> ProductSnapshot:
        return ProductSnapshot.objects.create(
            target=target,
            parse_status=SnapshotParseStatus.SUCCESS,
            source=SnapshotSource.PARSER,
            price=price,
            old_price=None,
            currency="RUB",
            is_available=is_available,
            rating=rating,
            reviews_count=reviews_count,
            title=title,
            seller_name="Test seller",
            brand="Test brand",
            raw_data={
                "source": "test",
            },
            checked_at=checked_at,
        )


class AlertRuleConstraintTests(
    AlertRuleTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.user = self.create_user(
            "alert-rule-constraint-user"
        )
        self.target = self.create_target(
            user=self.user,
        )

    def test_target_cannot_have_duplicate_alert_type_rules(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlertRule.objects.create(
                    user=self.user,
                    target=self.target,
                    alert_type=AlertType.PRICE_DROPPED,
                )

    def test_user_cannot_have_duplicate_global_rules(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AlertRule.objects.create(
                    user=self.user,
                    target=None,
                    alert_type=AlertType.PRICE_DROPPED,
                )

    def test_different_targets_can_have_same_alert_type(
        self,
    ):
        second_target = self.create_target(
            user=self.user,
            external_id="654321",
        )

        first_rule = AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )
        second_rule = AlertRule.objects.create(
            user=self.user,
            target=second_target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertNotEqual(
            first_rule.id,
            second_rule.id,
        )


class EffectiveAlertRuleTests(
    AlertRuleTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.user = self.create_user(
            "effective-alert-rule-user"
        )
        self.target = self.create_target(
            user=self.user,
        )

    def test_default_rule_is_used_when_custom_rule_does_not_exist(
        self,
    ):
        rule = get_effective_alert_rule(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertFalse(
            rule.is_custom,
        )
        self.assertTrue(
            rule.is_enabled,
        )
        self.assertEqual(
            rule.threshold_percent,
            Decimal("5.00"),
        )
        self.assertIsNone(
            rule.threshold_absolute,
        )
        self.assertEqual(
            rule.cooldown_minutes,
            360,
        )

    def test_global_rule_is_used_when_target_rule_does_not_exist(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("3.00"),
            threshold_absolute=Decimal("100.00"),
            cooldown_minutes=120,
            is_enabled=False,
        )

        rule = get_effective_alert_rule(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertTrue(
            rule.is_custom,
        )
        self.assertFalse(
            rule.is_enabled,
        )
        self.assertEqual(
            rule.threshold_percent,
            Decimal("3.00"),
        )
        self.assertEqual(
            rule.threshold_absolute,
            Decimal("100.00"),
        )
        self.assertEqual(
            rule.cooldown_minutes,
            120,
        )

    def test_target_rule_has_priority_over_global_rule(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("10.00"),
            cooldown_minutes=360,
            is_enabled=False,
        )
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("2.00"),
            cooldown_minutes=30,
            is_enabled=True,
        )

        rule = get_effective_alert_rule(
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
        )

        self.assertTrue(
            rule.is_custom,
        )
        self.assertTrue(
            rule.is_enabled,
        )
        self.assertEqual(
            rule.threshold_percent,
            Decimal("2.00"),
        )
        self.assertEqual(
            rule.cooldown_minutes,
            30,
        )


class AlertRuleApplicationTests(
    AlertRuleTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.user = self.create_user(
            "alert-rule-application-user"
        )
        self.target = self.create_target(
            user=self.user,
        )
        self.base_time = timezone.now() - timedelta(hours=1)

    def test_default_price_rule_blocks_change_below_five_percent(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("96.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )
        self.assertEqual(
            Alert.objects.count(),
            0,
        )
        self.assertEqual(
            OutboxEvent.objects.count(),
            0,
        )

    def test_default_price_rule_allows_five_percent_change(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("95.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.PRICE_DROPPED,
        )
        self.assertEqual(
            OutboxEvent.objects.count(),
            1,
        )

        outbox_event = OutboxEvent.objects.get()

        self.assertEqual(
            outbox_event.topic,
            "alert.created",
        )
        self.assertEqual(
            outbox_event.payload["alert_id"],
            str(alerts[0].id),
        )
        self.assertEqual(
            outbox_event.payload["target_id"],
            str(self.target.id),
        )

    def test_disabled_target_rule_blocks_alert(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            cooldown_minutes=0,
            is_enabled=False,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("50.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )
        self.assertFalse(
            Alert.objects.exists(),
        )
        self.assertFalse(
            OutboxEvent.objects.exists(),
        )

    def test_disabled_global_rule_blocks_alert(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            cooldown_minutes=0,
            is_enabled=False,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("50.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )

    def test_enabled_target_rule_overrides_disabled_global_rule(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=None,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            cooldown_minutes=0,
            is_enabled=False,
        )
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("2.00"),
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("97.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.PRICE_DROPPED,
        )

    def test_custom_percent_threshold_allows_small_price_change(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("2.00"),
            threshold_absolute=None,
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("97.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.PRICE_DROPPED,
        )
        self.assertEqual(
            alerts[0].new_value["percent_change"],
            "-3.00",
        )

    def test_absolute_threshold_blocks_price_change(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("5.00"),
            threshold_absolute=Decimal("10.00"),
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("94.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )

    def test_price_alert_is_created_when_both_thresholds_are_reached(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("5.00"),
            threshold_absolute=Decimal("10.00"),
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("80.00"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.PRICE_DROPPED,
        )

    def test_default_rating_rule_blocks_change_below_point_one(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            rating=Decimal("4.50"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            rating=Decimal("4.59"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )

    def test_default_rating_rule_allows_point_one_change(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            rating=Decimal("4.50"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            rating=Decimal("4.60"),
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.RATING_CHANGED,
        )

    def test_default_reviews_rule_blocks_change_below_ten(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            reviews_count=100,
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            reviews_count=109,
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            alerts,
            [],
        )

    def test_default_reviews_rule_allows_change_of_ten(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            reviews_count=100,
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            reviews_count=110,
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.REVIEWS_COUNT_CHANGED,
        )

    def test_availability_change_creates_alert_by_default(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            is_available=False,
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            is_available=True,
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.BECAME_AVAILABLE,
        )

    def test_title_change_creates_alert_by_default(
        self,
    ):
        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            title="Old product title",
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            title="New product title",
        )

        alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(alerts),
            1,
        )
        self.assertEqual(
            alerts[0].alert_type,
            AlertType.TITLE_CHANGED,
        )

    def test_cooldown_blocks_repeated_alert_type(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            threshold_absolute=None,
            cooldown_minutes=360,
            is_enabled=True,
        )

        first_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        first_drop_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("90.00"),
        )

        first_alerts = create_alerts_for_snapshot(
            snapshot=first_drop_snapshot,
        )

        self.assertEqual(
            len(first_alerts),
            1,
        )

        recovery_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=2),
            price=Decimal("100.00"),
        )
        second_drop_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=3),
            price=Decimal("90.00"),
        )

        self.assertIsNotNone(
            first_snapshot,
        )
        self.assertIsNotNone(
            recovery_snapshot,
        )

        second_alerts = create_alerts_for_snapshot(
            snapshot=second_drop_snapshot,
        )

        self.assertEqual(
            second_alerts,
            [],
        )
        self.assertEqual(
            Alert.objects.filter(
                alert_type=AlertType.PRICE_DROPPED,
            ).count(),
            1,
        )

    def test_zero_cooldown_allows_repeated_alert_type(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            threshold_absolute=None,
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        first_drop_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("90.00"),
        )

        first_alerts = create_alerts_for_snapshot(
            snapshot=first_drop_snapshot,
        )

        self.assertEqual(
            len(first_alerts),
            1,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=2),
            price=Decimal("100.00"),
        )
        second_drop_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=3),
            price=Decimal("90.00"),
        )

        second_alerts = create_alerts_for_snapshot(
            snapshot=second_drop_snapshot,
        )

        self.assertEqual(
            len(second_alerts),
            1,
        )
        self.assertEqual(
            Alert.objects.filter(
                alert_type=AlertType.PRICE_DROPPED,
            ).count(),
            2,
        )
        self.assertNotEqual(
            first_alerts[0].dedup_key,
            second_alerts[0].dedup_key,
        )

    def test_same_snapshot_cannot_create_duplicate_alert(
        self,
    ):
        AlertRule.objects.create(
            user=self.user,
            target=self.target,
            alert_type=AlertType.PRICE_DROPPED,
            threshold_percent=Decimal("0.00"),
            threshold_absolute=None,
            cooldown_minutes=0,
            is_enabled=True,
        )

        self.create_snapshot(
            target=self.target,
            checked_at=self.base_time,
            price=Decimal("100.00"),
        )
        current_snapshot = self.create_snapshot(
            target=self.target,
            checked_at=self.base_time + timedelta(minutes=1),
            price=Decimal("90.00"),
        )

        first_alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )
        second_alerts = create_alerts_for_snapshot(
            snapshot=current_snapshot,
        )

        self.assertEqual(
            len(first_alerts),
            1,
        )
        self.assertEqual(
            second_alerts,
            [],
        )
        self.assertEqual(
            Alert.objects.count(),
            1,
        )
        self.assertEqual(
            OutboxEvent.objects.count(),
            1,
        )
