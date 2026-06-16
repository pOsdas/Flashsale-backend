from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    ProductSnapshot,
    SnapshotParseStatus,
    SnapshotSource,
)
from app.api.v1.monitoring.services.alert_service import create_alerts_for_snapshot
from app.core.logging import get_logger


logger = get_logger(__name__)


def create_product_snapshot(
    *,
    target: MonitoringTarget,
    parse_status: str = SnapshotParseStatus.SUCCESS,
    source: str = SnapshotSource.PARSER,
    price: Decimal | int | str | None = None,
    old_price: Decimal | int | str | None = None,
    currency: str = "RUB",
    is_available: bool | None = None,
    rating: Decimal | int | str | None = None,
    reviews_count: int | None = None,
    title: str = "",
    seller_name: str = "",
    brand: str = "",
    external_id: str = "",
    raw_data: dict[str, Any] | None = None,
    error_message: str = "",
    checked_at=None,
) -> ProductSnapshot:
    checked_at = checked_at or timezone.now()

    with transaction.atomic():
        snapshot = ProductSnapshot.objects.create(
            target=target,
            parse_status=parse_status,
            source=source,
            price=_to_decimal_or_none(price),
            old_price=_to_decimal_or_none(old_price),
            currency=currency,
            is_available=is_available,
            rating=_to_decimal_or_none(rating),
            reviews_count=reviews_count,
            title=title,
            seller_name=seller_name,
            brand=brand,
            raw_data=raw_data or {},
            error_message=error_message,
            checked_at=checked_at,
        )

        _update_target_from_snapshot(
            target=target,
            snapshot=snapshot,
            external_id=external_id,
        )

    if snapshot.parse_status == SnapshotParseStatus.SUCCESS:
        try:
            create_alerts_for_snapshot(snapshot=snapshot)
        except Exception as exc:
            logger.exception(
                "monitoring alerts creation failed after successful snapshot",
                extra={
                    "service": "monitoring",
                    "target_id": str(target.id),
                    "snapshot_id": str(snapshot.id),
                    "error": str(exc),
                },
            )

    logger.info(
        "monitoring product snapshot created",
        extra={
            "service": "monitoring",
            "target_id": str(target.id),
            "snapshot_id": str(snapshot.id),
            "parse_status": snapshot.parse_status,
            "source": snapshot.source,
            "price": str(snapshot.price) if snapshot.price is not None else None,
        },
    )

    return snapshot


def _update_target_from_snapshot(
    *,
    target: MonitoringTarget,
    snapshot: ProductSnapshot,
    external_id: str = "",
) -> None:
    target.last_checked_at = snapshot.checked_at
    target.next_check_at = snapshot.checked_at + timedelta(
        minutes=target.check_interval_minutes,
    )

    if external_id:
        target.external_id = external_id

    if snapshot.title:
        target.title = snapshot.title

    if snapshot.seller_name:
        target.seller_name = snapshot.seller_name

    if snapshot.brand:
        target.brand = snapshot.brand

    if snapshot.parse_status == SnapshotParseStatus.SUCCESS:
        target.last_error = ""
    else:
        target.last_error = snapshot.error_message

    target.save(
        update_fields=[
            "external_id",
            "title",
            "seller_name",
            "brand",
            "last_checked_at",
            "next_check_at",
            "last_error",
            "updated_at",
        ]
    )


def _to_decimal_or_none(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None

    return Decimal(str(value))
