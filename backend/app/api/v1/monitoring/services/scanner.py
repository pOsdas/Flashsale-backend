from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.product_cache import (
    ProductCacheBusyError,
    ProductCacheService,
)
from app.api.v1.monitoring.services.snapshot_service import create_product_snapshot
from app.core.logging import get_logger


logger = get_logger(__name__)


class MonitoringScanner:
    def __init__(self, batch_size: int = 50) -> None:
        self.batch_size = batch_size
        self.product_cache_service = ProductCacheService()

    def run_once(self) -> int:
        targets = self._get_due_targets()

        processed_count = 0

        for target in targets:
            self._process_target(target=target)
            processed_count += 1

        if processed_count:
            logger.info(
                "monitoring scanner iteration finished",
                extra={
                    "service": "monitoring_scanner",
                    "processed_count": processed_count,
                },
            )

        return processed_count

    def _get_due_targets(self) -> list[MonitoringTarget]:
        now = timezone.now()

        return list(
            MonitoringTarget.objects
            .filter(
                is_active=True,
                status=MonitoringTargetStatus.ACTIVE,
                next_check_at__lte=now,
            )
            .order_by("next_check_at")[: self.batch_size]
        )

    def _process_target(self, *, target: MonitoringTarget) -> None:
        logger.info(
            "monitoring target processing started",
            extra={
                "service": "monitoring_scanner",
                "target_id": str(target.id),
                "marketplace": target.marketplace,
                "url": target.url,
            },
        )

        try:
            cache_result = self.product_cache_service.get_or_refresh_product(
                target=target,
            )
            fetched_data = cache_result.product

            create_product_snapshot(
                target=target,
                parse_status=SnapshotParseStatus.SUCCESS,
                source=cache_result.source,
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
                raw_data=cache_result.build_snapshot_raw_data(),
            )

            logger.info(
                "monitoring target processed successfully",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "cache_source": cache_result.source,
                    "cache_is_stale": cache_result.is_stale,
                    "effective_cache_minutes": cache_result.effective_cache_minutes,
                },
            )

        except ProductCacheBusyError as exc:
            logger.warning(
                "monitoring target postponed because product cache refresh is already in progress",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "error": str(exc),
                },
            )

            self._postpone_target_after_cache_busy(
                target=target,
                error=str(exc),
            )

        except Exception as exc:
            logger.exception(
                "monitoring target processing failed",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "error": str(exc),
                },
            )

            self._mark_target_failed(
                target=target,
                error=str(exc),
            )

    def _postpone_target_after_cache_busy(
            self,
            *,
            target: MonitoringTarget,
            error: str,
    ) -> None:
        with transaction.atomic():
            locked_target = (
                MonitoringTarget.objects
                .select_for_update()
                .get(id=target.id)
            )

            locked_target.next_check_at = timezone.now() + timedelta(minutes=5)
            locked_target.last_error = error
            locked_target.save(
                update_fields=[
                    "next_check_at",
                    "last_error",
                    "updated_at",
                ]
            )

    def _mark_target_failed(
            self,
            *,
            target: MonitoringTarget,
            error: str,
    ) -> None:
        with transaction.atomic():
            locked_target = (
                MonitoringTarget.objects
                .select_for_update()
                .get(id=target.id)
            )

            locked_target.last_checked_at = timezone.now()
            locked_target.next_check_at = timezone.now()
            locked_target.last_error = error
            locked_target.status = MonitoringTargetStatus.FAILED
            locked_target.save(
                update_fields=[
                    "last_checked_at",
                    "next_check_at",
                    "last_error",
                    "status",
                    "updated_at",
                ]
            )

            create_product_snapshot(
                target=locked_target,
                parse_status=SnapshotParseStatus.PARSE_ERROR,
                error_message=error,
                raw_data={
                    "source": "monitoring_scanner",
                    "error": error,
                },
            )
