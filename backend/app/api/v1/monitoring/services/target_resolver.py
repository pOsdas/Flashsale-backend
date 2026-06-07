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
    normalized_url = normalize_product_url(url)

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
                "next_check_at": timezone.now(),
            },
        )

        if not created:
            target.role = role
            target.check_interval_minutes = check_interval_minutes
            target.status = MonitoringTargetStatus.ACTIVE
            target.is_active = True
            target.last_error = ""
            target.save(
                update_fields=[
                    "role",
                    "check_interval_minutes",
                    "status",
                    "is_active",
                    "last_error",
                    "updated_at",
                ]
            )

    return ResolvedMonitoringTarget(
        target=target,
        created=created,
    )
