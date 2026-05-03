from typing import Any

from app.api.v1.orders.models import OutboxEvent


def create_outbox_event(
        *,
        topic: str,
        payload: dict[str, Any],
) -> OutboxEvent:
    return OutboxEvent.objects.create(
        topic=topic,
        payload=payload,
    )
