from django.conf import settings
from django.core.management.base import BaseCommand
from prometheus_client import start_http_server

from app.api.v1.notifications.rabbitmq.notification_consumer import (
    NotificationRabbitMQConsumer,
)
from app.core.logging import get_logger


logger = get_logger(__name__)


class Command(BaseCommand):
    help = "Run RabbitMQ notification consumer"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=int(
                getattr(
                    settings,
                    "NOTIFICATION_CONSUMER_METRICS_PORT",
                    8011,
                )
            ),
            help="Prometheus metrics HTTP port",
        )

    def handle(self, *args, **options) -> None:
        metrics_port = options["metrics_port"]

        start_http_server(metrics_port)

        logger.info(
            "Notification consumer metrics server started",
            extra={
                "service": "notification_consumer",
                "metrics_port": metrics_port,
            },
        )

        consumer = NotificationRabbitMQConsumer()
        consumer.start()
