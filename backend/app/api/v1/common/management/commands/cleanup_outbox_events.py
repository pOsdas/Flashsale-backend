from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.api.v1.orders.models import OutboxEvent


class Command(BaseCommand):
    help = "Deletes old processed outbox events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete processed events older than this number of days",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many events would be deleted without deleting them",
        )

    def handle(self, *args, **options):
        days = options["days"]
        dry_run = options["dry_run"]

        if days <= 0:
            self.stderr.write(
                self.style.ERROR("--days must be a positive integer")
            )
            return

        threshold = timezone.now() - timedelta(days=days)

        queryset = OutboxEvent.objects.filter(
            status=OutboxEvent.Status.PROCESSED,
            # processed_at__lt=threshold,
            published_at__lt=threshold,
        )

        count = queryset.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {count} processed outbox event(s) older than {days} day(s) would be deleted."
                )
            )
            return

        deleted_count, _ = queryset.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} processed outbox event(s) older than {days} day(s)."
            )
        )
