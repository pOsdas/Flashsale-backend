from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import (
    AlertType,
    SnapshotParseStatus,
)
from app.api.v1.notifications.telegram.target_history_presenter import (
    build_target_history_text,
)


class TelegramTargetHistoryPresenterTests(SimpleTestCase):
    def test_builds_snapshot_and_alert_history(self) -> None:
        checked_at = datetime(
            2026,
            6,
            27,
            12,
            0,
            tzinfo=timezone.utc,
        )
        history = SimpleNamespace(
            target=SimpleNamespace(
                title="Тестовый товар",
                external_id="123",
                url="https://example.com",
                marketplace="wb",
            ),
            snapshots=(
                SimpleNamespace(
                    checked_at=checked_at,
                    parse_status=SnapshotParseStatus.SUCCESS,
                    price=Decimal("1999.00"),
                    currency="RUB",
                    is_available=True,
                ),
            ),
            alerts=(
                SimpleNamespace(
                    alert_type=AlertType.PRICE_DROPPED,
                    title="Цена снизилась",
                    message="Цена товара снизилась",
                    old_value="2499",
                    new_value="1999",
                    created_at=checked_at,
                ),
            ),
        )

        text = build_target_history_text(history=history)

        self.assertIn("Тестовый товар", text)
        self.assertIn("1 999 ₽", text)
        self.assertIn("2 499 ₽ → 1 999 ₽", text)
        self.assertIn("Цена снизилась", text)
