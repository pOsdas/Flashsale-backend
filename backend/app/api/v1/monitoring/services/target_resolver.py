from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
)
from app.api.v1.monitoring.services.url_normalizer import normalize_product_url


@dataclass(frozen=True, slots=True)
class ResolvedMonitoringTarget:
    target: MonitoringTarget
    created: bool


def resolve_monitoring_target(
    *,
    user,
    marketplace: str,
    url: str,
    role: str,
    check_interval_minutes: int,
) -> ResolvedMonitoringTarget:
    """
    Create a monitoring target or reactivate an existing one.

    A target is identified by:
    - user;
    - marketplace;
    - normalized product URL.

    Repeated creation is idempotent from the user's point of view:
    the existing target is updated and reactivated instead of creating
    another logically identical target.
    """

    normalized_url = normalize_product_url(url)
    current_time = timezone.now()

    with transaction.atomic():
        target, created = MonitoringTarget.objects.get_or_create(
            user=user,
            marketplace=marketplace,
            url=normalized_url,
            defaults={
                "role": role,
                "check_interval_minutes": check_interval_minutes,
                "status": MonitoringTargetStatus.ACTIVE,
                "is_active": True,
                "next_check_at": current_time,
                "last_error": "",
            },
        )

        if created:
            return ResolvedMonitoringTarget(
                target=target,
                created=True,
            )

        target = (
            MonitoringTarget.objects
            .select_for_update()
            .get(id=target.id)
        )

        target.role = role
        target.check_interval_minutes = check_interval_minutes
        target.status = MonitoringTargetStatus.ACTIVE
        target.is_active = True
        target.next_check_at = current_time
        target.last_error = ""

        target.save(
            update_fields=[
                "role",
                "check_interval_minutes",
                "status",
                "is_active",
                "next_check_at",
                "last_error",
                "updated_at",
            ]
        )

    return ResolvedMonitoringTarget(
        target=target,
        created=False,
    )
