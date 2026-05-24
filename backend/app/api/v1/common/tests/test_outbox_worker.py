from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.api.v1.orders.models import OutboxEvent
from app.api.v1.common.outbox_worker import OutboxWorker


class OutboxWorkerTests(TestCase):
    def test_worker_processes_pending_event_successfully(self):
        event = OutboxEvent.objects.create(
            topic="order.created",
            payload={
                "order_id": 1,
                "total_cents": 1500,
            },
            status=OutboxEvent.Status.PENDING,
        )

        with patch("app.api.v1.common.outbox_handlers.handle_order_created") as mocked_handler:
            processed_count = OutboxWorker(batch_size=10).run_once()

        event.refresh_from_db()

        self.assertEqual(processed_count, 1)
        self.assertEqual(event.status, OutboxEvent.Status.PROCESSED)
        self.assertEqual(event.attempts, 0)
        self.assertEqual(event.error, "")
        self.assertIsNotNone(event.processed_at)

        mocked_handler.assert_called_once_with(
            {
                "order_id": 1,
                "total_cents": 1500,
            }
        )

    def test_worker_does_not_process_event_without_handler_and_marks_it_for_retry(self):
        event = OutboxEvent.objects.create(
            topic="unknown.topic",
            payload={"value": "test"},
            status=OutboxEvent.Status.PENDING,
            attempts=0,
            max_attempts=5,
        )

        before_run = timezone.now()

        processed_count = OutboxWorker(batch_size=10).run_once()

        event.refresh_from_db()

        self.assertEqual(processed_count, 1)
        self.assertEqual(event.status, OutboxEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("No handler registered for topic", event.error)
        self.assertIsNone(event.processed_at)
        self.assertGreater(event.available_at, before_run)

    def test_worker_marks_event_as_failed_after_max_attempts(self):
        event = OutboxEvent.objects.create(
            topic="unknown.topic",
            payload={"value": "test"},
            status=OutboxEvent.Status.PENDING,
            attempts=4,
            max_attempts=5,
        )

        processed_count = OutboxWorker(batch_size=10).run_once()

        event.refresh_from_db()

        self.assertEqual(processed_count, 1)
        self.assertEqual(event.status, OutboxEvent.Status.FAILED)
        self.assertEqual(event.attempts, 5)
        self.assertIn("No handler registered for topic", event.error)
        self.assertIsNone(event.processed_at)

    def test_worker_retries_event_when_handler_raises_exception(self):
        event = OutboxEvent.objects.create(
            topic="order.created",
            payload={"order_id": 1},
            status=OutboxEvent.Status.PENDING,
            attempts=0,
            max_attempts=5,
        )

        with patch("app.api.v1.common.outbox_handlers.handle_order_created") as mocked_handler:
            mocked_handler.side_effect = RuntimeError("test error")

            processed_count = OutboxWorker(batch_size=10).run_once()

        event.refresh_from_db()

        self.assertEqual(processed_count, 1)
        self.assertEqual(event.status, OutboxEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertEqual(event.error, "test error")
        self.assertIsNone(event.processed_at)
        self.assertGreater(event.available_at, timezone.now())

        mocked_handler.assert_called_once_with({"order_id": 1})

    def test_worker_does_not_process_events_that_are_not_available_yet(self):
        OutboxEvent.objects.create(
            topic="order.created",
            payload={"order_id": 1},
            status=OutboxEvent.Status.PENDING,
            available_at=timezone.now() + timezone.timedelta(minutes=10),
        )

        processed_count = OutboxWorker(batch_size=10).run_once()

        self.assertEqual(processed_count, 0)

    def test_worker_respects_batch_size(self):
        for index in range(3):
            OutboxEvent.objects.create(
                topic="order.created",
                payload={"order_id": index + 1},
                status=OutboxEvent.Status.PENDING,
            )

        with patch("app.api.v1.common.outbox_handlers.handle_order_created") as mocked_handler:
            processed_count = OutboxWorker(batch_size=2).run_once()

        self.assertEqual(processed_count, 2)
        self.assertEqual(mocked_handler.call_count, 2)
        self.assertEqual(
            OutboxEvent.objects.filter(status=OutboxEvent.Status.PROCESSED).count(),
            2,
        )
        self.assertEqual(
            OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING).count(),
            1,
        )

    def test_worker_does_not_process_already_processed_events(self):
        OutboxEvent.objects.create(
            topic="order.created",
            payload={"order_id": 1},
            status=OutboxEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )

        with patch("app.api.v1.common.outbox_handlers.handle_order_created") as mocked_handler:
            processed_count = OutboxWorker(batch_size=10).run_once()

        self.assertEqual(processed_count, 0)
        mocked_handler.get.assert_not_called()


class OutboxWorkerIntegrationTests(TestCase):
    def test_worker_processes_real_events_flow(self):
        OutboxEvent.objects.create(
            topic="order.created",
            payload={
                "order_id": 101,
            },
            status=OutboxEvent.Status.PENDING,
        )

        OutboxEvent.objects.create(
            topic="order.status_changed",
            payload={
                "order_id": 101,
                "new_status": "paid",
            },
            status=OutboxEvent.Status.PENDING,
        )

        with (
            patch(
                "app.api.v1.common.outbox_handlers.handle_order_created"
            ) as order_created_handler,
            patch(
                "app.api.v1.common.outbox_handlers.handle_order_status_changed"
            ) as status_changed_handler,
        ):
            processed_count = OutboxWorker(batch_size=10).run_once()

        self.assertEqual(processed_count, 2)

        self.assertEqual(
            OutboxEvent.objects.filter(
                status=OutboxEvent.Status.PROCESSED,
            ).count(),
            2,
        )

        order_created_handler.assert_called_once_with(
            {
                "order_id": 101,
            }
        )

        status_changed_handler.assert_called_once_with(
            {
                "order_id": 101,
                "new_status": "paid",
            }
        )