from dataclasses import dataclass
from uuid import UUID

from app.api.v1.monitoring.models import (
    Alert,
    MonitoringTarget,
    ProductSnapshot,
)
from app.api.v1.monitoring.services.target_service import (
    get_monitoring_target_for_user,
)


DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT = 5
MAX_TELEGRAM_TARGET_HISTORY_LIMIT = 10


@dataclass(frozen=True, slots=True)
class MonitoringTargetHistory:
    target: MonitoringTarget
    snapshots: tuple[ProductSnapshot, ...]
    alerts: tuple[Alert, ...]


def get_monitoring_target_history(
    *,
    user,
    target_id: UUID | str,
    limit: int = DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT,
) -> MonitoringTargetHistory:
    target = get_monitoring_target_for_user(
        user=user,
        target_id=target_id,
    )
    normalized_limit = _normalize_limit(limit)

    snapshots = tuple(
        ProductSnapshot.objects
        .filter(target=target)
        .order_by("-checked_at", "-created_at")[:normalized_limit]
    )
    alerts = tuple(
        Alert.objects
        .filter(
            user=user,
            target=target,
        )
        .select_related("snapshot")
        .order_by("-created_at", "-id")[:normalized_limit]
    )

    return MonitoringTargetHistory(
        target=target,
        snapshots=snapshots,
        alerts=alerts,
    )


def _normalize_limit(limit: int) -> int:
    try:
        normalized_limit = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT

    if normalized_limit < 1:
        return DEFAULT_TELEGRAM_TARGET_HISTORY_LIMIT

    return min(
        normalized_limit,
        MAX_TELEGRAM_TARGET_HISTORY_LIMIT,
    )
