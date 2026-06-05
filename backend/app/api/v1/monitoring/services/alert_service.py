from django.db import IntegrityError, transaction

from app.api.v1.monitoring.models import Alert, ProductSnapshot
from app.api.v1.monitoring.services.change_detector import (
    AlertCandidate,
    detect_snapshot_changes,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


def create_alerts_for_snapshot(
    *,
    snapshot: ProductSnapshot,
) -> list[Alert]:
    previous_snapshot = _get_previous_snapshot(snapshot=snapshot)

    candidates = detect_snapshot_changes(
        previous_snapshot=previous_snapshot,
        current_snapshot=snapshot,
    )

    created_alerts: list[Alert] = []

    for candidate in candidates:
        alert = _create_alert_from_candidate(
            snapshot=snapshot,
            candidate=candidate,
        )

        if alert is not None:
            created_alerts.append(alert)

    if created_alerts:
        logger.info(
            "monitoring alerts created",
            extra={
                "service": "monitoring",
                "target_id": str(snapshot.target_id),
                "snapshot_id": str(snapshot.id),
                "alerts_count": len(created_alerts),
            },
        )

    return created_alerts


def _get_previous_snapshot(
    *,
    snapshot: ProductSnapshot,
) -> ProductSnapshot | None:
    return (
        ProductSnapshot.objects
        .filter(
            target=snapshot.target,
            checked_at__lt=snapshot.checked_at,
        )
        .order_by("-checked_at")
        .first()
    )


def _create_alert_from_candidate(
    *,
    snapshot: ProductSnapshot,
    candidate: AlertCandidate,
) -> Alert | None:
    try:
        with transaction.atomic():
            return Alert.objects.create(
                user=snapshot.target.user,
                target=snapshot.target,
                snapshot=snapshot,
                alert_type=candidate.alert_type,
                severity=candidate.severity,
                title=candidate.title,
                message=candidate.message,
                old_value=candidate.old_value,
                new_value=candidate.new_value,
                dedup_key=candidate.dedup_key,
            )

    except IntegrityError:
        logger.info(
            "monitoring alert skipped by deduplication",
            extra={
                "service": "monitoring",
                "target_id": str(snapshot.target_id),
                "snapshot_id": str(snapshot.id),
                "dedup_key": candidate.dedup_key,
            },
        )
        return None
