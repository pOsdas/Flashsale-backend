from typing import Any

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.fetcher_client import (
    MonitoringFetcherError,
    build_monitoring_fetcher_client,
)
from app.api.v1.monitoring.services.target_resolver import resolve_monitoring_target
from app.api.v1.monitoring.services.snapshot_service import create_product_snapshot
from app.core.logging import get_logger


logger = get_logger(__name__)


def create_monitoring_target(
    *,
    user,
    validated_data: dict[str, Any],
) -> MonitoringTarget:
    resolved_target = resolve_monitoring_target(
        user=user,
        marketplace=validated_data["marketplace"],
        url=validated_data["url"],
        role=validated_data["role"],
        check_interval_minutes=validated_data["check_interval_minutes"],
    )

    target = resolved_target.target
    created = resolved_target.created

    fetcher_client = build_monitoring_fetcher_client()

    try:
        fetched_product = fetcher_client.fetch_target(target=target)

        create_product_snapshot(
            target=target,
            parse_status=SnapshotParseStatus.SUCCESS,
            price=fetched_product.price,
            old_price=fetched_product.old_price,
            currency=fetched_product.currency,
            is_available=fetched_product.is_available,
            rating=fetched_product.rating,
            reviews_count=fetched_product.reviews_count,
            title=fetched_product.title,
            seller_name=fetched_product.seller_name,
            brand=fetched_product.brand,
            external_id=fetched_product.external_id,
            raw_data=fetched_product.raw_data,
            error_message="",
        )

    except MonitoringFetcherError as exc:
        create_product_snapshot(
            target=target,
            parse_status=SnapshotParseStatus.PARSE_ERROR,
            raw_data={
                "source": "go_fetcher",
                "error": str(exc),
            },
            error_message=str(exc),
        )

    target.refresh_from_db()

    logger.info(
        "monitoring target resolved",
        extra={
            "service": "monitoring",
            "target_id": str(target.id),
            "user_id": str(user.id),
            "marketplace": target.marketplace,
            "target_created": created,
        },
    )

    return target
