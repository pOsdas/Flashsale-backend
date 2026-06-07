from django.conf import settings
from django.db import transaction

from app.api.v1.monitoring.models import MonitoringTarget
from app.api.v1.monitoring.services.fetcher_client import HttpMonitoringFetcherClient
from app.api.v1.monitoring.services.snapshot_service import create_product_snapshot
from app.api.v1.monitoring.services.url_normalizer import normalize_product_url


class FetchProductService:
    def __init__(
        self,
        *,
        user,
        marketplace: str,
        url: str,
        role: str,
        check_interval_minutes: int,
    ) -> None:
        self.user = user
        self.marketplace = marketplace
        self.url = url
        self.role = role
        self.check_interval_minutes = check_interval_minutes

    def execute(self) -> dict:
        normalized_url = normalize_product_url(self.url)

        with transaction.atomic():
            target, created = MonitoringTarget.objects.get_or_create(
                user=self.user,
                marketplace=self.marketplace,
                url=normalized_url,
                defaults={
                    "role": self.role,
                    "check_interval_minutes": self.check_interval_minutes,
                    "is_active": True,
                },
            )

            if not created:
                target.role = self.role
                target.check_interval_minutes = self.check_interval_minutes
                target.is_active = True
                target.last_error = ""
                target.save(
                    update_fields=[
                        "role",
                        "check_interval_minutes",
                        "is_active",
                        "last_error",
                        "updated_at",
                    ]
                )

        fetcher_client = HttpMonitoringFetcherClient(
            base_url=settings.GO_FETCHER_BASE_URL,
            product_endpoint=settings.GO_FETCHER_PRODUCT_ENDPOINT,
            api_key=settings.GO_FETCHER_API_KEY,
            timeout_seconds=settings.GO_FETCHER_TIMEOUT_SECONDS,
        )

        try:
            fetched_data = fetcher_client.fetch_target(target=target)
        except Exception as e:
            target.last_error = str(e)

            target.save(
                update_fields=[
                    "last_error",
                    "updated_at",
                ]
            )

            raise

        snapshot = create_product_snapshot(
            target=target,
            external_id=fetched_data.external_id,
            price=fetched_data.price,
            old_price=fetched_data.old_price,
            currency=fetched_data.currency,
            is_available=fetched_data.is_available,
            rating=fetched_data.rating,
            reviews_count=fetched_data.reviews_count,
            title=fetched_data.title,
            seller_name=fetched_data.seller_name,
            brand=fetched_data.brand,
            raw_data=fetched_data.raw_data,
        )

        alerts_count = snapshot.alerts.count()

        return {
            "target_id": target.id,
            "snapshot_id": snapshot.id,
            "alerts_count": alerts_count,
            "product": {
                "external_id": snapshot.target.external_id,
                "title": snapshot.title,
                "seller_name": snapshot.seller_name,
                "brand": snapshot.brand,
                "price": str(snapshot.price) if snapshot.price is not None else None,
                "old_price": str(snapshot.old_price) if snapshot.old_price is not None else None,
                "currency": snapshot.currency,
                "is_available": snapshot.is_available,
                "rating": str(snapshot.rating) if snapshot.rating is not None else None,
                "reviews_count": snapshot.reviews_count,
                "checked_at": snapshot.checked_at,
            },
            "target_created": created,
        }
