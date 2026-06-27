from typing import Any

from django.db.models import Q

from app.api.v1.monitoring.models import MonitoringTarget


def find_existing_monitoring_target(
    *,
    user: Any,
    marketplace: str,
    external_id: str,
    url: str,
) -> MonitoringTarget | None:
    normalized_external_id = str(external_id).strip()
    normalized_url = str(url).strip()

    identity_query = Q()

    if normalized_external_id:
        identity_query |= Q(
            external_id=normalized_external_id,
        )

    if normalized_url:
        identity_query |= Q(
            url=normalized_url,
        )

    if not identity_query:
        return None

    return (
        MonitoringTarget.objects
        .filter(
            user=user,
            marketplace=marketplace,
        )
        .filter(identity_query)
        .order_by("-created_at")
        .first()
    )
