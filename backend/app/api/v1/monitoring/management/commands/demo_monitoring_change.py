from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.api.v1.monitoring.models import (
    Alert,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
)
from app.api.v1.monitoring.services.snapshot_service import create_product_snapshot


class Command(BaseCommand):
    help = "Creates demo monitoring target, snapshots and alerts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="User email. If empty, first existing user will be used.",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="https://www.wildberries.ru/catalog/123456789/detail.aspx",
            help="Product URL for demo target.",
        )
        parser.add_argument(
            "--marketplace",
            type=str,
            default=Marketplace.WILDBERRIES,
            choices=[choice[0] for choice in Marketplace.choices],
            help="Marketplace code.",
        )

    def handle(self, *args, **options):
        user = self._get_user(email=options["email"])

        target = MonitoringTarget.objects.create(
            user=user,
            marketplace=options["marketplace"],
            role=MonitoringTargetRole.COMPETITOR,
            url=options["url"],
            external_id="123456789",
            title="Демо товар Flashsale Signals",
            seller_name="Demo Seller",
            brand="Demo Brand",
            check_interval_minutes=60,
            next_check_at=timezone.now(),
            is_active=True,
        )

        first_snapshot = create_product_snapshot(
            target=target,
            external_id="123456789",
            price=Decimal("1000.00"),
            old_price=Decimal("1200.00"),
            is_available=True,
            rating=Decimal("4.80"),
            reviews_count=100,
            title="Демо товар Flashsale Signals",
            seller_name="Demo Seller",
            brand="Demo Brand",
            raw_data={
                "source": "demo",
                "snapshot_number": 1,
            },
        )

        second_snapshot = create_product_snapshot(
            target=target,
            external_id="123456789",
            price=Decimal("850.00"),
            old_price=Decimal("1200.00"),
            is_available=True,
            rating=Decimal("4.70"),
            reviews_count=115,
            title="Демо товар Flashsale Signals обновленный",
            seller_name="Demo Seller",
            brand="Demo Brand",
            raw_data={
                "source": "demo",
                "snapshot_number": 2,
            },
        )

        alerts = Alert.objects.filter(
            target=target,
        ).order_by("created_at")

        self.stdout.write(
            self.style.SUCCESS("Demo monitoring scenario created")
        )
        self.stdout.write(f"User: {user}")
        self.stdout.write(f"Target ID: {target.id}")
        self.stdout.write(f"First snapshot ID: {first_snapshot.id}")
        self.stdout.write(f"Second snapshot ID: {second_snapshot.id}")
        self.stdout.write(f"Created alerts: {alerts.count()}")

        for alert in alerts:
            self.stdout.write(
                f"- [{alert.severity}] {alert.alert_type}: {alert.message}"
            )

    def _get_user(self, *, email: str):
        User = get_user_model()

        if email:
            user = User.objects.filter(email=email).first()

            if user is None:
                raise CommandError(f"User with email={email!r} not found")

            return user

        user = User.objects.order_by("id").first()

        if user is None:
            raise CommandError(
                "No users found. Create a user before running this command."
            )

        return user
