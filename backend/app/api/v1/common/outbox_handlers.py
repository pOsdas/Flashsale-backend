from typing import Any, Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


def handle_order_created(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling order.created event",
        extra={"payload": payload},
    )


def handle_order_status_changed(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling order.statis_changed event",
        extra={"payload": payload},
    )


def handle_catalog_import_completed(payload: dict[str, Any]) -> None:
    logger.info(
        "Handling catalog.import.completed event",
        extra={"payload": payload},
    )


def get_outbox_handlers() -> dict[str, Callable[[dict[str, Any]], None]]:
    return {
        "order.created": handle_order_created,
        "order.status_changed": handle_order_status_changed,
        "catalog.import.completed": handle_catalog_import_completed,
    }
