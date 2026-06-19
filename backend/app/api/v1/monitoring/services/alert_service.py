from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from app.api.v1.monitoring.models import (
    Alert,
    MonitoringTarget,
    ProductSnapshot,
)
from app.api.v1.monitoring.services.alert_rule_service import (
    evaluate_alert_candidate,
)
from app.api.v1.monitoring.services.change_detector import (
    AlertCandidate,
    detect_snapshot_changes,
)
from app.api.v1.orders.models import OutboxEvent
from app.core.logging import get_logger


logger = get_logger(__name__)


def create_alerts_for_snapshot(
    *,
    snapshot: ProductSnapshot,
) -> list[Alert]:
    previous_snapshot = _get_previous_snapshot(
        snapshot=snapshot,
    )

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
            (
                MonitoringTarget.objects
                .select_for_update()
                .only("id")
                .get(id=snapshot.target_id)
            )

            decision = evaluate_alert_candidate(
                snapshot=snapshot,
                candidate=candidate,
            )

            if not decision.allowed:
                logger.info(
                    "monitoring alert skipped by target rule",
                    extra={
                        "service": "monitoring",
                        "target_id": str(snapshot.target_id),
                        "snapshot_id": str(snapshot.id),
                        "alert_type": candidate.alert_type,
                        "reason": decision.reason,
                        "rule_is_custom": decision.rule.is_custom,
                        "rule_is_enabled": decision.rule.is_enabled,
                        "threshold_percent": (
                            str(decision.rule.threshold_percent)
                            if decision.rule.threshold_percent
                            is not None
                            else None
                        ),
                        "threshold_absolute": (
                            str(decision.rule.threshold_absolute)
                            if decision.rule.threshold_absolute
                            is not None
                            else None
                        ),
                        "cooldown_minutes": (
                            decision.rule.cooldown_minutes
                        ),
                        "candidate_change_percent": (
                            str(candidate.change_percent)
                            if candidate.change_percent is not None
                            else None
                        ),
                        "candidate_change_absolute": (
                            str(candidate.change_absolute)
                            if candidate.change_absolute is not None
                            else None
                        ),
                    },
                )
                return None

            alert = Alert.objects.create(
                user=snapshot.target.user,
                target=snapshot.target,
                snapshot=snapshot,
                alert_type=candidate.alert_type,
                severity=candidate.severity,
                title=candidate.title,
                message=candidate.message,
                old_value=_to_json_safe(
                    candidate.old_value,
                ),
                new_value=_to_json_safe(
                    candidate.new_value,
                ),
                dedup_key=candidate.dedup_key,
            )

            OutboxEvent.objects.create(
                topic="alert.created",
                payload={
                    "alert_id": str(alert.id),
                    "user_id": str(alert.user_id),
                    "target_id": str(alert.target_id),
                    "snapshot_id": str(snapshot.id),
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                },
            )

            return alert

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


def _to_json_safe(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _to_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _to_json_safe(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _to_json_safe(item)
            for item in value
        ]

    return value
