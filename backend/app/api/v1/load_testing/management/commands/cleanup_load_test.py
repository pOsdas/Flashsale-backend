from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from app.api.v1.monitoring.models import ProductCacheEntry
from app.api.v1.orders.models import OutboxEvent


class Command(BaseCommand):
    help = "Delete synthetic Load Lab data from the current database"

    def handle(self, *args, **options):
        user_model = get_user_model()
        load_user_ids = list(
            user_model.objects.filter(
                username__startswith="loadtest_",
            ).values_list("id", flat=True)
        )
        load_user_ids_as_text = [str(user_id) for user_id in load_user_ids]
        deleted_users, details = user_model.objects.filter(
            id__in=load_user_ids,
        ).delete()
        deleted_cache, _ = ProductCacheEntry.objects.filter(
            external_id__startswith="lt-",
        ).delete()
        deleted_outbox, _ = OutboxEvent.objects.filter(
            payload__user_id__in=load_user_ids_as_text,
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted users/relations={deleted_users}, "
                f"cache={deleted_cache}, outbox={deleted_outbox}"
            )
        )
        if details:
            self.stdout.write(str(details))
