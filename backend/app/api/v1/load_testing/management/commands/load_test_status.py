import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from app.api.v1.monitoring.models import Alert, MonitoringTarget, ProductSnapshot
from app.api.v1.notifications.models import NotificationDelivery
from app.api.v1.orders.models import OutboxEvent


class Command(BaseCommand):
    help = "Print a machine-readable Load Lab status summary"

    def handle(self, *args, **options):
        user_model = get_user_model()
        users = user_model.objects.filter(username__startswith="loadtest_")
        targets = MonitoringTarget.objects.filter(user__in=users)
        summary = {
            "timestamp": timezone.now().isoformat(),
            "users": users.count(),
            "targets": targets.count(),
            "due_targets": targets.filter(
                is_active=True,
                next_check_at__lte=timezone.now(),
            ).count(),
            "snapshots": ProductSnapshot.objects.filter(
                target__user__in=users,
            ).count(),
            "alerts": Alert.objects.filter(user__in=users).count(),
            "outbox": dict(
                OutboxEvent.objects.values_list("status")
                .annotate(total=Count("id"))
            ),
            "deliveries": dict(
                NotificationDelivery.objects.filter(user__in=users)
                .values_list("status")
                .annotate(total=Count("id"))
            ),
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
