from abc import ABC, abstractmethod

from django.conf import settings

from app.api.v1.common.outbox_handlers import get_outbox_handlers
from app.api.v1.common.rabbitmq.publisher import build_rabbitmq_publisher
from app.api.v1.orders.models import OutboxEvent
from app.core.logging import get_logger


logger = get_logger(__name__)


class OutboxDispatcher(ABC):
    @abstractmethod
    def dispatch(self, event: OutboxEvent) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class LocalOutboxDispatcher(OutboxDispatcher):
    def dispatch(self, event: OutboxEvent) -> None:
        handlers = get_outbox_handlers()
        handler = handlers.get(event.topic)

        if handler is None:
            raise RuntimeError(f"No handler registered for topic: {event.topic}")

        handler(event.payload)

        logger.info(
            "outbox event dispatched locally",
            extra={
                "service": "outbox_worker",
                "event_id": str(event.id),
                "topic": event.topic,
                "mode": "local",
            },
        )


class RabbitMQOutboxDispatcher(OutboxDispatcher):
    def __init__(self) -> None:
        self.publisher = build_rabbitmq_publisher()

    def dispatch(self, event: OutboxEvent) -> None:
        self.publisher.publish(
            routing_key=event.topic,
            payload={
                "event_id": str(event.id),
                "topic": event.topic,
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            },
            message_id=str(event.id),
        )

        logger.info(
            "outbox event dispatched to rabbitmq",
            extra={
                "service": "outbox_worker",
                "event_id": str(event.id),
                "topic": event.topic,
                "mode": "rabbitmq",
            },
        )

    def close(self) -> None:
        self.publisher.close()


def build_outbox_dispatcher() -> OutboxDispatcher:
    mode = settings.OUTBOX_DISPATCH_MODE.lower().strip()

    if mode == "local":
        return LocalOutboxDispatcher()

    if mode == "rabbitmq":
        return RabbitMQOutboxDispatcher()

    raise RuntimeError(
        f"Unsupported OUTBOX_DISPATCH_MODE={settings.OUTBOX_DISPATCH_MODE!r}. "
        "Allowed values: local, rabbitmq."
    )
