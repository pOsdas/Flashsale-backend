import time
import signal

from django.core.management.base import BaseCommand


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

    def handle(self, *args, **options):
        from app.api.v1.common.outbox_worker import OutboxWorker

        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        once = options["once"]
        batch_size = options["batch_size"]
        sleep_seconds = options["sleep"]

        worker = OutboxWorker(batch_size=batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                f"Outbox worker started: once={once}, batch_size={batch_size}, sleep={sleep_seconds}"
            )
        )

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

            time.sleep(sleep_seconds)

    def _stop(self, signum, frame):
        self.stdout.write(
            self.style.WARNING(
                f"Shutdown signal received: {signum}. Finishing current iteration..."
            )
        )
        self.running = False

