from typing import Any, Callable

from app.api.v1.notifications.consumers import AlertCreatedNotificationConsumer
from app.core.logging import get_logger


logger = get_logger(__name__)


def handle_order_created(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling order.created event",
        extra={
            "service": "outbox_handler",
            "topic": "order.created",
            "payload": payload,
        },
    )


def handle_order_status_changed(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling order.status_changed event",
        extra={
            "service": "outbox_handler",
            "topic": "order.status_changed",
            "payload": payload,
        },
    )


def handle_catalog_import_completed(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling catalog.import.completed event",
        extra={
            "service": "outbox_handler",
            "topic": "catalog.import.completed",
            "payload": payload,
        },
    )


def handle_alert_created(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling alert.created event",
        extra={
            "service": "outbox_handler",
            "topic": "alert.created",
            "payload": payload,
        },
    )

    AlertCreatedNotificationConsumer().handle(payload)


def get_outbox_handlers() -> dict[str, Callable[[dict[str, Any]], None]]:
    return {
        "order.created": handle_order_created,
        "order.status_changed": handle_order_status_changed,
        "catalog.import.completed": handle_catalog_import_completed,
        "alert.created": handle_alert_created,
    }
