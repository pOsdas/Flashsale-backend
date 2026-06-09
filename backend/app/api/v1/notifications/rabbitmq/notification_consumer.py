import json
import signal
import time
from typing import Any

import pika
from django.conf import settings

from app.api.v1.common.outbox_handlers import get_outbox_handlers
from app.api.v1.notifications.notification_metrics import (
    NOTIFICATION_MESSAGE_PROCESSING_DURATION_SECONDS,
    NOTIFICATION_MESSAGES_TOTAL,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class NotificationRabbitMQConsumer:
    def __init__(self) -> None:
        self.rabbitmq_url = settings.RABBITMQ_URL
        self.exchange_name = getattr(
            settings,
            "RABBITMQ_OUTBOX_EXCHANGE",
            "flashsale.outbox",
        )
        self.queue_name = getattr(
            settings,
            "NOTIFICATION_RABBITMQ_QUEUE",
            "flashsale.notifications",
        )
        self.dead_letter_exchange_name = getattr(
            settings,
            "NOTIFICATION_RABBITMQ_DLX",
            "flashsale.notifications.dlx",
        )
        self.dead_letter_queue_name = getattr(
            settings,
            "NOTIFICATION_RABBITMQ_DLQ",
            "flashsale.notifications.dlq",
        )
        self.routing_keys = getattr(
            settings,
            "NOTIFICATION_RABBITMQ_ROUTING_KEYS",
            ["alert.created"],
        )
        self.prefetch_count = int(
            getattr(
                settings,
                "NOTIFICATION_RABBITMQ_PREFETCH_COUNT",
                10,
            )
        )

        self.connection: pika.BlockingConnection | None = None
        self.channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        self.should_stop = False

    def start(self) -> None:
        self._register_signal_handlers()
        self._connect()
        self._declare_topology()

        assert self.channel is not None

        self.channel.basic_qos(prefetch_count=self.prefetch_count)
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )

        logger.info(
            "Notification RabbitMQ consumer started",
            extra={
                "service": "notification_consumer",
                "queue": self.queue_name,
                "exchange": self.exchange_name,
                "routing_keys": self.routing_keys,
                "prefetch_count": self.prefetch_count,
            },
        )

        try:
            self.channel.start_consuming()
        finally:
            self.close()

    def _register_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_stop_signal)
        signal.signal(signal.SIGTERM, self._handle_stop_signal)

    def _handle_stop_signal(self, signum, frame) -> None:
        self.should_stop = True

        logger.info(
            "Notification RabbitMQ consumer stopping",
            extra={
                "service": "notification_consumer",
                "signal": signum,
            },
        )

        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()

    def _connect(self) -> None:
        parameters = pika.URLParameters(self.rabbitmq_url)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()

    def _declare_topology(self) -> None:
        assert self.channel is not None

        self.channel.exchange_declare(
            exchange=self.exchange_name,
            exchange_type="topic",
            durable=True,
        )

        self.channel.exchange_declare(
            exchange=self.dead_letter_exchange_name,
            exchange_type="topic",
            durable=True,
        )

        self.channel.queue_declare(
            queue=self.dead_letter_queue_name,
            durable=True,
        )

        self.channel.queue_bind(
            queue=self.dead_letter_queue_name,
            exchange=self.dead_letter_exchange_name,
            routing_key="#",
        )

        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.dead_letter_exchange_name,
            },
        )

        for routing_key in self.routing_keys:
            self.channel.queue_bind(
                queue=self.queue_name,
                exchange=self.exchange_name,
                routing_key=routing_key,
            )

    def _on_message(
        self,
        channel: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        started_at = time.monotonic()
        topic = method.routing_key or "unknown"

        try:
            message = self._decode_message(body=body)
            event_topic = message["topic"]
            event_payload = message["payload"]
            event_id = message.get("event_id", "")

            self._handle_event(
                event_id=event_id,
                topic=event_topic,
                payload=event_payload,
            )

        except Exception as exc:
            NOTIFICATION_MESSAGES_TOTAL.labels(
                topic=topic,
                status="failed",
            ).inc()

            logger.exception(
                "Notification RabbitMQ message processing failed",
                extra={
                    "service": "notification_consumer",
                    "routing_key": topic,
                    "message_id": getattr(properties, "message_id", ""),
                    "error": str(exc),
                },
            )

            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=False,
            )
            return

        finally:
            duration = time.monotonic() - started_at
            NOTIFICATION_MESSAGE_PROCESSING_DURATION_SECONDS.labels(
                topic=topic,
            ).observe(duration)

        NOTIFICATION_MESSAGES_TOTAL.labels(
            topic=topic,
            status="processed",
        ).inc()

        channel.basic_ack(
            delivery_tag=method.delivery_tag,
        )

    def _decode_message(self, body: bytes) -> dict[str, Any]:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("RabbitMQ message body is not valid JSON") from exc

        if not isinstance(decoded, dict):
            raise ValueError("RabbitMQ message body must be JSON object")

        if "topic" not in decoded:
            raise ValueError("RabbitMQ message does not contain topic")

        if "payload" not in decoded:
            raise ValueError("RabbitMQ message does not contain payload")

        if not isinstance(decoded["payload"], dict):
            raise ValueError("RabbitMQ message payload must be JSON object")

        return decoded

    def _handle_event(
        self,
        event_id: str,
        topic: str,
        payload: dict[str, Any],
    ) -> None:
        handlers = get_outbox_handlers()
        handler = handlers.get(topic)

        if handler is None:
            raise RuntimeError(f"No handler registered for topic: {topic}")

        logger.info(
            "Notification RabbitMQ event handling started",
            extra={
                "service": "notification_consumer",
                "event_id": event_id,
                "topic": topic,
                "payload": payload,
            },
        )

        handler(payload)

        logger.info(
            "Notification RabbitMQ event handled",
            extra={
                "service": "notification_consumer",
                "event_id": event_id,
                "topic": topic,
            },
        )

    def close(self) -> None:
        if self.channel and self.channel.is_open:
            self.channel.close()

        if self.connection and self.connection.is_open:
            self.connection.close()

        logger.info(
            "Notification RabbitMQ consumer closed",
            extra={
                "service": "notification_consumer",
            },
        )
