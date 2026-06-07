import os
import signal
import time

from django.core.management.base import BaseCommand

from app.api.v1.monitoring.services.scanner import MonitoringScanner
from app.core.logging import get_logger


logger = get_logger(__name__)


class Command(BaseCommand):
    help = "Runs monitoring scanner"

    def __init__(self):
        super().__init__()
        self.running = True

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run scanner once and exit",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of monitoring targets to process per iteration",
        )
        parser.add_argument(
            "--sleep",
            type=int,
            default=30,
            help="Sleep time between iterations in seconds",
        )

    def handle(self, *args, **options):
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        once = options["once"]
        batch_size = int(
            os.environ.get(
                "MONITORING_SCANNER_BATCH_SIZE",
                options["batch_size"],
            )
        )
        sleep_seconds = int(
            os.environ.get(
                "MONITORING_SCANNER_SLEEP_SECONDS",
                options["sleep"],
            )
        )

        scanner = MonitoringScanner(batch_size=batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                f"Monitoring scanner started: once={once}, "
                f"batch_size={batch_size}, sleep={sleep_seconds}"
            )
        )

        logger.info(
            "monitoring scanner started",
            extra={
                "service": "monitoring_scanner",
                "once": once,
                "batch_size": batch_size,
                "sleep_seconds": sleep_seconds,
            },
        )

        while self.running:
            processed_count = scanner.run_once()

            if processed_count:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Processed monitoring targets: {processed_count}"
                    )
                )

            if once:
                break

            if self.running:
                time.sleep(sleep_seconds)

        self.stdout.write(
            self.style.WARNING("Monitoring scanner stopped gracefully")
        )

    def _stop(self, signum, frame):
        self.stdout.write(
            self.style.WARNING(
                f"Shutdown signal received: {signum}. Finishing current iteration..."
            )
        )
        self.running = False
