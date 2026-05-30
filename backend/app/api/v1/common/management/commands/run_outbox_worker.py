import os
import time
import signal

from django.core.management.base import BaseCommand
from prometheus_client import start_http_server

from app.core.logging import get_logger


logger = get_logger(__name__)


class Command(BaseCommand):
    help = "Runs outbox worker"

    def __init__(self):
        super().__init__()
        self.running = True

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run worker once and exit",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of events to process per iteration",
        )
        parser.add_argument(
            "--sleep",
            type=int,
            default=5,
            help="Sleep time between iterations in seconds",
        )
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=9100,
        )

    def handle(self, *args, **options):
        from app.api.v1.common.outbox_worker import OutboxWorker

        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        once = options["once"]
        batch_size = options["batch_size"]
        sleep_seconds = options["sleep"]

        metrics_port = int(
            os.environ.get(
                "OUTBOX_METRICS_PORT",
                options["metrics_port"],
            )
        )

        if not once:
            start_http_server(metrics_port)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Outbox metrics server started on port {metrics_port}"
                )
            )

        worker = OutboxWorker(batch_size=batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                f"Outbox worker started: once={once}, batch_size={batch_size}, sleep={sleep_seconds}"
            )
        )

        logger.info(
            "outbox worker started",
            extra={
                "service": "outbox_worker",
                "once": once,
                "batch_size": batch_size,
                "sleep_seconds": sleep_seconds,
            },
        )

        try:
            while self.running:
                processed_count = worker.run_once()

                if processed_count:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Processed outbox events: {processed_count}"
                        )
                    )

                if once:
                    break

                if self.running:
                    time.sleep(sleep_seconds)

        finally:
            worker.close()

            self.stdout.write(
                self.style.WARNING("Outbox worker stopped gracefully")
            )

    def _stop(self, signum, frame):
        self.stdout.write(
            self.style.WARNING(
                f"Shutdown signal received: {signum}. Finishing current iteration..."
            )
        )
        self.running = False

