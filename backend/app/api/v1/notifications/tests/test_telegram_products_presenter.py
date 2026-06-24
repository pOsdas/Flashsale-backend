from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import MonitoringTargetStatus
from app.api.v1.monitoring.services.target_query_service import (
    MonitoringTargetListItem,
    MonitoringTargetPage,
)
from app.api.v1.notifications.telegram.keyboards import (
    build_products_keyboard,
)
from app.api.v1.notifications.telegram.products_presenter import (
    build_products_page_text,
)


class TelegramProductsPresenterTests(SimpleTestCase):
    def test_builds_products_page_and_action_keyboard(self) -> None:
        target = SimpleNamespace(
            id=uuid4(),
            title="Тестовый товар",
            external_id="123",
            url="https://www.wildberries.ru/catalog/123/detail.aspx",
            marketplace="wb",
            status=MonitoringTargetStatus.ACTIVE,
            is_active=True,
            check_interval_minutes=60,
        )
        target_page = MonitoringTargetPage(
            items=(
                MonitoringTargetListItem(
                    target=target,
                    latest_price=Decimal("1999.00"),
                    latest_currency="RUB",
                    latest_is_available=True,
                    latest_rating=Decimal("4.80"),
                    latest_reviews_count=10,
                    latest_checked_at=datetime(
                        2026,
                        6,
                        24,
                        18,
                        30,
                        tzinfo=timezone.utc,
                    ),
                    latest_parse_status="success",
                    latest_source="cache",
                ),
            ),
            page=1,
            page_size=3,
            total_items=1,
            total_pages=1,
        )

        text = build_products_page_text(
            target_page=target_page,
        )
        keyboard = build_products_keyboard(
            target_page=target_page,
        )

        self.assertIn("Тестовый товар", text)
        self.assertIn("1 999 ₽", text)
        self.assertIn("✅ активно", text)
        self.assertEqual(
            keyboard["inline_keyboard"][0][0]["text"],
            "🔄 Проверить 1",
        )
        self.assertIn(
            str(target.id),
            keyboard["inline_keyboard"][0][0]["callback_data"],
        )

    def test_builds_empty_products_page(self) -> None:
        target_page = MonitoringTargetPage(
            items=(),
            page=1,
            page_size=3,
            total_items=0,
            total_pages=0,
        )

        text = build_products_page_text(
            target_page=target_page,
        )
        keyboard = build_products_keyboard(
            target_page=target_page,
        )

        self.assertIn("пока нет отслеживаемых товаров", text)
        self.assertEqual(keyboard["inline_keyboard"], [])
