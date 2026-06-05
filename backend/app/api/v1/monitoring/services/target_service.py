from typing import Any

from django.db import transaction

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.snapshot_service import create_product_snapshot
from app.core.logging import get_logger


logger = get_logger(__name__)


def create_monitoring_target(
    *,
    user,
    validated_data: dict[str, Any],
) -> MonitoringTarget:
    with transaction.atomic():
        target = MonitoringTarget.objects.create(
            user=user,
            status=MonitoringTargetStatus.ACTIVE,
            is_active=True,
            **validated_data,
        )

        create_product_snapshot(
            target=target,
            parse_status=SnapshotParseStatus.PARSE_ERROR,
            raw_data={
                "source": "target_created",
                "reason": "fetcher_not_connected_yet",
            },
            error_message=(
                "Initial snapshot placeholder created. "
                "Real marketplace fetcher is not connected yet."
            ),
        )

    logger.info(
        "monitoring target created",
        extra={
            "service": "monitoring",
            "target_id": str(target.id),
            "user_id": str(user.id),
            "marketplace": target.marketplace,
        },
    )

    return target
