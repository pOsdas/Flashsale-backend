from datetime import timedelta

from django.db import transaction, models
from django.utils import timezone

from app.core.logging import get_logger
from app.api.v1.orders.models import OutboxEvent
from app.api.v1.common.outbox_handlers import get_outbox_handlers


logger = get_logger(__name__)


class OutboxWorker:
    def __init__(self, batch_size: int = 50) -> None:
        self.batch_size = batch_size

    def run_once(self) -> int:
        events = self._claim_events()

        processed_count = 0

        for event in events:
            self._process_event(event)
            processed_count += 1

        return processed_count

    def _claim_events(self) -> list[OutboxEvent]:
        now = timezone.now()

        with transaction.atomic():
            events = list(
                OutboxEvent.objects
                .select_for_update(skip_locked=True)
                .filter(
                    status=OutboxEvent.Status.PENDING,
                    attempts__lt=models.F("max_attempts"),
                    available_at__lte=now,
                )
                .order_by("created_at")[: self.batch_size]
            )

            event_ids = [event.id for event in events]

            if event_ids:
                OutboxEvent.objects.filter(id__in=event_ids).update(
                    status=OutboxEvent.Status.PROCESSING,
                    updated_at=now,
                )

        return events

    def _process_event(self, event: OutboxEvent) -> None:
        handlers = get_outbox_handlers()
        handler = handlers.get(event.topic)

        if handler is None:
            self._mark_failed(
                event=event,
                error=f"No handler registered for topic: {event.topic}",
            )
            return

        try:
            handler(event.payload)
        except Exception as exc:
            logger.exception(
                "Outbox event processing failed",
                extra={
                    "event_id": event.id,
                    "topic": event.topic,
                    "attempts": event.attempts,
                },
            )
            self._mark_failed(event=event, error=str(exc))
            return

        self._mark_processed(event)

    def _mark_processed(self, event: OutboxEvent) -> None:
        now = timezone.now()

        OutboxEvent.objects.filter(id=event.id).update(
            status=OutboxEvent.Status.PROCESSED,
            processed_at=now,
            published_at=now,
            updated_at=now,
            error="",
        )

        logger.info(
            "Outbox event processed",
            extra={
                "event_id": event.id,
                "topic": event.topic,
            },
        )

    def _mark_failed(self, event: OutboxEvent, error: str) -> None:
        now = timezone.now()
        next_attempt = event.attempts + 1

        if next_attempt >= event.max_attempts:
            next_status = OutboxEvent.Status.FAILED
            available_at = now
        else:
            next_status = OutboxEvent.Status.PENDING
            available_at = now + self._get_retry_delay(next_attempt)

        OutboxEvent.objects.filter(id=event.id).update(
            status=next_status,
            attempts=next_attempt,
            error=error[:5000],
            available_at=available_at,
            updated_at=now,
        )

    def _get_retry_delay(self, attempt: int) -> timedelta:
        seconds = min(60 * (2 ** (attempt - 1)), 3600)
        return timedelta(seconds=seconds)
