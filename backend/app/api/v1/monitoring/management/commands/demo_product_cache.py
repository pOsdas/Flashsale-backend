from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test.utils import override_settings
from django.utils import timezone

from app.api.v1.monitoring.models import (
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    MonitoringTargetStatus,
    ProductCacheEntry,
    ProductSnapshot,
)
from app.api.v1.monitoring.services.scanner import MonitoringScanner


class Command(BaseCommand):
    help = "Demo command for checking shared product cache and cache expiration in monitoring scanner."

    def handle(self, *args, **options) -> None:
        user = self._get_user()

        marketplace = Marketplace.WILDBERRIES
        external_id = "demo-shared-cache-product"
        url = "https://www.wildberries.ru/catalog/demo-shared-cache-product/detail.aspx"

        self._cleanup_demo_data(
            marketplace=marketplace,
            external_id=external_id,
        )

        target_a, target_b = self._create_demo_targets(
            user=user,
            marketplace=marketplace,
            external_id=external_id,
            url=url,
        )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=== FIRST SCANNER RUN ==="))
        self.stdout.write("Expected: first target from parser, second target from cache.")

        self._run_scanner_with_fake_fetcher()

        self._print_cache_entries(
            marketplace=marketplace,
            external_id=external_id,
        )
        self._print_snapshots(
            marketplace=marketplace,
            external_id=external_id,
            title="Snapshots after first run",
        )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=== MAKING CACHE EXPIRED ==="))
        self._expire_cache_entry(
            marketplace=marketplace,
            external_id=external_id,
            minutes_ago=61,
        )

        self._make_targets_due_again(
            target_a=target_a,
            target_b=target_b,
        )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=== SECOND SCANNER RUN AFTER CACHE EXPIRATION ==="))
        self.stdout.write("Expected: one target refreshes parser again, the next target uses fresh cache again.")

        self._run_scanner_with_fake_fetcher()

        self._print_cache_entries(
            marketplace=marketplace,
            external_id=external_id,
        )
        self._print_snapshots(
            marketplace=marketplace,
            external_id=external_id,
            title="All snapshots after second run",
        )

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=== EXPECTED RESULT ==="))
        self.stdout.write(
            "1. There must be exactly one ProductCacheEntry for marketplace=wb and "
            "external_id=demo-shared-cache-product."
        )
        self.stdout.write(
            "2. First scanner run should create two snapshots: source=parser, then source=cache."
        )
        self.stdout.write(
            "3. After cache expiration, second scanner run should create two more snapshots: "
            "source=parser, then source=cache."
        )
        self.stdout.write(
            "4. ProductCacheEntry.effective_cache_minutes must stay 60, because targets have intervals 60 and 120."
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Product cache expiration demo finished."))

    def _get_user(self):
        User = get_user_model()

        user = User.objects.order_by("id").first()
        if user is None:
            raise RuntimeError(
                "Cannot run demo_product_cache because there are no users in database. "
                "Create at least one user first."
            )

        return user

    def _cleanup_demo_data(
            self,
            *,
            marketplace: str,
            external_id: str,
    ) -> None:
        self.stdout.write("Cleaning old demo data...")

        demo_targets = MonitoringTarget.objects.filter(
            marketplace=marketplace,
            external_id=external_id,
        )

        ProductSnapshot.objects.filter(
            target__in=demo_targets,
        ).delete()

        demo_targets.delete()

        ProductCacheEntry.objects.filter(
            marketplace=marketplace,
            external_id=external_id,
        ).delete()

    def _create_demo_targets(
            self,
            *,
            user,
            marketplace: str,
            external_id: str,
            url: str,
    ) -> tuple[MonitoringTarget, MonitoringTarget]:
        self.stdout.write("Creating two monitoring targets for the same product...")

        target_a = MonitoringTarget.objects.create(
            user=user,
            marketplace=marketplace,
            role=MonitoringTargetRole.COMPETITOR,
            status=MonitoringTargetStatus.ACTIVE,
            url=url,
            external_id=external_id,
            title="Demo shared cache product",
            seller_name="Demo Seller",
            brand="Demo Brand",
            check_interval_minutes=60,
            is_active=True,
            next_check_at=timezone.now(),
        )

        target_b = MonitoringTarget.objects.create(
            user=user,
            marketplace=marketplace,
            role=MonitoringTargetRole.COMPETITOR,
            status=MonitoringTargetStatus.ACTIVE,
            url=url,
            external_id=external_id,
            title="Demo shared cache product",
            seller_name="Demo Seller",
            brand="Demo Brand",
            check_interval_minutes=120,
            is_active=True,
            next_check_at=timezone.now(),
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created target A: {target_a.id}, interval={target_a.check_interval_minutes} minutes"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created target B: {target_b.id}, interval={target_b.check_interval_minutes} minutes"
            )
        )

        return target_a, target_b

    def _run_scanner_with_fake_fetcher(self) -> None:
        self.stdout.write("Running monitoring scanner with fake fetcher...")

        with override_settings(MONITORING_FETCHER_MODE="fake"):
            scanner = MonitoringScanner(batch_size=10)
            processed_count = scanner.run_once()

        self.stdout.write(
            self.style.SUCCESS(
                f"Scanner processed targets: {processed_count}"
            )
        )

    def _expire_cache_entry(
            self,
            *,
            marketplace: str,
            external_id: str,
            minutes_ago: int,
    ) -> None:
        cache_entry = ProductCacheEntry.objects.get(
            marketplace=marketplace,
            external_id=external_id,
        )

        expired_parsed_at = timezone.now() - timedelta(minutes=minutes_ago)
        expired_expires_at = expired_parsed_at + timedelta(
            minutes=cache_entry.effective_cache_minutes,
        )

        cache_entry.parsed_at = expired_parsed_at
        cache_entry.expires_at = expired_expires_at
        cache_entry.save(
            update_fields=[
                "parsed_at",
                "expires_at",
                "updated_at",
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Cache entry was manually expired: "
                    f"parsed_at={cache_entry.parsed_at}, "
                    f"expires_at={cache_entry.expires_at}, "
                    f"effective_cache_minutes={cache_entry.effective_cache_minutes}"
                )
            )
        )

    def _make_targets_due_again(
            self,
            *,
            target_a: MonitoringTarget,
            target_b: MonitoringTarget,
    ) -> None:
        now = timezone.now()

        MonitoringTarget.objects.filter(
            id__in=[
                target_a.id,
                target_b.id,
            ],
        ).update(
            status=MonitoringTargetStatus.ACTIVE,
            is_active=True,
            next_check_at=now,
            last_error="",
            updated_at=now,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Both demo targets were made due again."
            )
        )

    def _print_cache_entries(
            self,
            *,
            marketplace: str,
            external_id: str,
    ) -> None:
        cache_entries = ProductCacheEntry.objects.filter(
            marketplace=marketplace,
            external_id=external_id,
        )

        self.stdout.write("")
        self.stdout.write("Product cache entries:")

        if not cache_entries.exists():
            self.stdout.write(self.style.ERROR("No ProductCacheEntry rows found."))
            return

        for cache_entry in cache_entries:
            self.stdout.write(
                self.style.SUCCESS(
                    (
                        f"id={cache_entry.id}, "
                        f"marketplace={cache_entry.marketplace}, "
                        f"external_id={cache_entry.external_id}, "
                        f"effective_cache_minutes={cache_entry.effective_cache_minutes}, "
                        f"parsed_at={cache_entry.parsed_at}, "
                        f"expires_at={cache_entry.expires_at}, "
                        f"last_success_at={cache_entry.last_success_at}"
                    )
                )
            )

    def _print_snapshots(
            self,
            *,
            marketplace: str,
            external_id: str,
            title: str,
    ) -> None:
        snapshots = (
            ProductSnapshot.objects
            .filter(
                target__marketplace=marketplace,
                target__external_id=external_id,
            )
            .select_related("target")
            .order_by("created_at")
        )

        self.stdout.write("")
        self.stdout.write(title + ":")

        if not snapshots.exists():
            self.stdout.write(self.style.ERROR("No ProductSnapshot rows found."))
            return

        for snapshot in snapshots:
            self.stdout.write(
                (
                    f"target_id={snapshot.target_id}, "
                    f"target_interval={snapshot.target.check_interval_minutes}, "
                    f"snapshot_id={snapshot.id}, "
                    f"parse_status={snapshot.parse_status}, "
                    f"source={snapshot.source}, "
                    f"price={snapshot.price}, "
                    f"checked_at={snapshot.checked_at}"
                )
            )
