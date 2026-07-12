from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
)


class Command(BaseCommand):
    help = "Make synthetic monitoring targets due now"

    def add_arguments(self, parser):
        parser.add_argument(
            "--overdue-seconds",
            type=int,
            default=1,
        )

    def handle(self, *args, **options):
        due_at = timezone.now() - timedelta(
            seconds=max(options["overdue_seconds"], 0)
        )
        updated = MonitoringTarget.objects.filter(
            user__username__startswith="loadtest_",
            is_active=True,
            status=MonitoringTargetStatus.ACTIVE,
        ).update(next_check_at=due_at)
        self.stdout.write(
            self.style.SUCCESS(f"Marked targets due: {updated}")
        )
