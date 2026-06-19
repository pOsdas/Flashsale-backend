from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
    ProductSnapshot,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.product_cache import (
    ProductCacheBusyError,
    ProductCacheService,
)
from app.api.v1.monitoring.services.snapshot_service import (
    create_product_snapshot,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MonitoringTargetProcessResult:
    """
    Result of a single monitoring target processing attempt.

    The scanner worker, REST API and Telegram bot can use the same
    processing method without duplicating the product fetching,
    snapshot creation and alert detection logic.
    """

    success: bool
    snapshot: ProductSnapshot | None = None
    alerts_count: int = 0
    cache_source: str = ""
    cache_is_stale: bool = False
    effective_cache_minutes: int | None = None
    error: str = ""
    busy: bool = False


class MonitoringScanner:
    def __init__(
        self,
        batch_size: int = 50,
        product_cache_service: ProductCacheService | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.product_cache_service = (
            product_cache_service or ProductCacheService()
        )

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
            .order_by("next_check_at")[:self.batch_size]
        )

    def _process_target(
        self,
        *,
        target: MonitoringTarget,
    ) -> MonitoringTargetProcessResult:
        """
        Backward-compatible scanner worker entry point.

        Existing scanner tests or integrations may still call this private
        method, while REST API and Telegram bot use process_target().
        """

        return self.process_target(
            target=target,
            force_refresh=False,
            postpone_on_busy=True,
            trigger="scanner",
        )

    def process_target(
        self,
        *,
        target: MonitoringTarget,
        force_refresh: bool = False,
        postpone_on_busy: bool = True,
        trigger: str = "scanner",
    ) -> MonitoringTargetProcessResult:
        """
        Process one monitoring target.

        force_refresh=False:
            Use a fresh shared cache entry when available.

        force_refresh=True:
            Request a new marketplace fetch through ProductCacheService.
            Redis locking and shared cache updating are still preserved.

        postpone_on_busy=True:
            Move the next scheduled check five minutes forward when another
            process currently refreshes the same product.

        postpone_on_busy=False:
            Do not change the target schedule. This mode is used by manual
            check-now requests.
        """

        logger.info(
            "monitoring target processing started",
            extra={
                "service": "monitoring_scanner",
                "target_id": str(target.id),
                "marketplace": target.marketplace,
                "url": target.url,
                "force_refresh": force_refresh,
                "trigger": trigger,
            },
        )

        try:
            cache_result = (
                self.product_cache_service
                .get_or_refresh_product(
                    target=target,
                    force_refresh=force_refresh,
                )
            )
            fetched_data = cache_result.product

            snapshot = create_product_snapshot(
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

            self._restore_target_after_success(
                target=target,
            )

            alerts_count = snapshot.alerts.count()

            logger.info(
                "monitoring target processed successfully",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "snapshot_id": str(snapshot.id),
                    "alerts_count": alerts_count,
                    "cache_source": cache_result.source,
                    "cache_is_stale": cache_result.is_stale,
                    "effective_cache_minutes": (
                        cache_result.effective_cache_minutes
                    ),
                    "force_refresh": force_refresh,
                    "trigger": trigger,
                },
            )

            return MonitoringTargetProcessResult(
                success=True,
                snapshot=snapshot,
                alerts_count=alerts_count,
                cache_source=cache_result.source,
                cache_is_stale=cache_result.is_stale,
                effective_cache_minutes=(
                    cache_result.effective_cache_minutes
                ),
            )

        except ProductCacheBusyError as exc:
            logger.warning(
                "monitoring target processing postponed because product cache refresh is busy",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "error": str(exc),
                    "postpone_on_busy": postpone_on_busy,
                    "trigger": trigger,
                },
            )

            if postpone_on_busy:
                self._postpone_target_after_cache_busy(
                    target=target,
                    error=str(exc),
                )

            return MonitoringTargetProcessResult(
                success=False,
                error=str(exc),
                busy=True,
            )

        except Exception as exc:
            logger.exception(
                "monitoring target processing failed",
                extra={
                    "service": "monitoring_scanner",
                    "target_id": str(target.id),
                    "marketplace": target.marketplace,
                    "error": str(exc),
                    "force_refresh": force_refresh,
                    "trigger": trigger,
                },
            )

            snapshot = self._mark_target_failed(
                target=target,
                error=str(exc),
            )

            return MonitoringTargetProcessResult(
                success=False,
                snapshot=snapshot,
                error=str(exc),
            )

    def _restore_target_after_success(
        self,
        *,
        target: MonitoringTarget,
    ) -> None:
        """
        Restore an active target from FAILED after a successful manual retry.

        A paused target remains paused because is_active=False.
        """

        with transaction.atomic():
            locked_target = (
                MonitoringTarget.objects
                .select_for_update()
                .get(id=target.id)
            )

            if (
                locked_target.is_active
                and locked_target.status
                == MonitoringTargetStatus.FAILED
            ):
                locked_target.status = MonitoringTargetStatus.ACTIVE
                locked_target.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
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

            locked_target.next_check_at = (
                timezone.now() + timedelta(minutes=5)
            )
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
    ) -> ProductSnapshot:
        """
        Save a failed snapshot.

        Active targets are moved to FAILED. Paused targets remain paused,
        because a manual check must not silently resume them.
        """

        with transaction.atomic():
            locked_target = (
                MonitoringTarget.objects
                .select_for_update()
                .get(id=target.id)
            )

            if locked_target.is_active:
                locked_target.status = MonitoringTargetStatus.FAILED
                locked_target.save(
                    update_fields=[
                        "status",
                        "updated_at",
                    ]
                )

            snapshot = create_product_snapshot(
                target=locked_target,
                parse_status=SnapshotParseStatus.PARSE_ERROR,
                error_message=error,
                raw_data={
                    "source": "monitoring_scanner",
                    "error": error,
                },
            )

        return snapshot
