from dataclasses import dataclass
from decimal import Decimal
from math import ceil
from typing import Any

from django.db.models import (
    BooleanField,
    CharField,
    DateTimeField,
    DecimalField,
    IntegerField,
    OuterRef,
    Subquery,
)

from app.api.v1.monitoring.models import (
    MonitoringTarget,
    ProductSnapshot,
)


DEFAULT_TELEGRAM_PRODUCTS_PAGE_SIZE = 3
MAX_TELEGRAM_PRODUCTS_PAGE_SIZE = 10


@dataclass(frozen=True, slots=True)
class MonitoringTargetListItem:
    target: MonitoringTarget
    latest_price: Decimal | None
    latest_currency: str
    latest_is_available: bool | None
    latest_rating: Decimal | None
    latest_reviews_count: int | None
    latest_checked_at: Any | None
    latest_parse_status: str | None
    latest_source: str | None


@dataclass(frozen=True, slots=True)
class MonitoringTargetPage:
    items: tuple[MonitoringTargetListItem, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int

    @property
    def has_previous(self) -> bool:
        return self.total_pages > 0 and self.page > 1

    @property
    def has_next(self) -> bool:
        return self.total_pages > 0 and self.page < self.total_pages


def list_monitoring_targets_for_user(
    *,
    user,
    page: int = 1,
    page_size: int = DEFAULT_TELEGRAM_PRODUCTS_PAGE_SIZE,
) -> MonitoringTargetPage:
    normalized_page_size = _normalize_page_size(page_size)

    latest_snapshot = (
        ProductSnapshot.objects
        .filter(target_id=OuterRef("pk"))
        .order_by("-checked_at", "-created_at")
    )

    queryset = (
        MonitoringTarget.objects
        .filter(user=user)
        .annotate(
            telegram_latest_price=Subquery(
                latest_snapshot.values("price")[:1],
                output_field=DecimalField(
                    max_digits=12,
                    decimal_places=2,
                ),
            ),
            telegram_latest_currency=Subquery(
                latest_snapshot.values("currency")[:1],
                output_field=CharField(max_length=10),
            ),
            telegram_latest_is_available=Subquery(
                latest_snapshot.values("is_available")[:1],
                output_field=BooleanField(),
            ),
            telegram_latest_rating=Subquery(
                latest_snapshot.values("rating")[:1],
                output_field=DecimalField(
                    max_digits=4,
                    decimal_places=2,
                ),
            ),
            telegram_latest_reviews_count=Subquery(
                latest_snapshot.values("reviews_count")[:1],
                output_field=IntegerField(),
            ),
            telegram_latest_checked_at=Subquery(
                latest_snapshot.values("checked_at")[:1],
                output_field=DateTimeField(),
            ),
            telegram_latest_parse_status=Subquery(
                latest_snapshot.values("parse_status")[:1],
                output_field=CharField(max_length=30),
            ),
            telegram_latest_source=Subquery(
                latest_snapshot.values("source")[:1],
                output_field=CharField(max_length=32),
            ),
        )
        .order_by("-created_at", "-id")
    )

    total_items = queryset.count()

    if total_items == 0:
        return MonitoringTargetPage(
            items=(),
            page=1,
            page_size=normalized_page_size,
            total_items=0,
            total_pages=0,
        )

    total_pages = ceil(total_items / normalized_page_size)
    normalized_page = _normalize_page(
        page=page,
        total_pages=total_pages,
    )
    offset = (normalized_page - 1) * normalized_page_size
    targets = tuple(
        queryset[offset:offset + normalized_page_size]
    )

    items = tuple(
        MonitoringTargetListItem(
            target=target,
            latest_price=getattr(
                target,
                "telegram_latest_price",
                None,
            ),
            latest_currency=(
                getattr(
                    target,
                    "telegram_latest_currency",
                    None,
                )
                or "RUB"
            ),
            latest_is_available=getattr(
                target,
                "telegram_latest_is_available",
                None,
            ),
            latest_rating=getattr(
                target,
                "telegram_latest_rating",
                None,
            ),
            latest_reviews_count=getattr(
                target,
                "telegram_latest_reviews_count",
                None,
            ),
            latest_checked_at=getattr(
                target,
                "telegram_latest_checked_at",
                None,
            ),
            latest_parse_status=getattr(
                target,
                "telegram_latest_parse_status",
                None,
            ),
            latest_source=getattr(
                target,
                "telegram_latest_source",
                None,
            ),
        )
        for target in targets
    )

    return MonitoringTargetPage(
        items=items,
        page=normalized_page,
        page_size=normalized_page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


def _normalize_page_size(page_size: int) -> int:
    try:
        normalized_page_size = int(page_size)
    except (TypeError, ValueError):
        return DEFAULT_TELEGRAM_PRODUCTS_PAGE_SIZE

    if normalized_page_size < 1:
        return DEFAULT_TELEGRAM_PRODUCTS_PAGE_SIZE

    return min(
        normalized_page_size,
        MAX_TELEGRAM_PRODUCTS_PAGE_SIZE,
    )


def _normalize_page(
    *,
    page: int,
    total_pages: int,
) -> int:
    try:
        normalized_page = int(page)
    except (TypeError, ValueError):
        normalized_page = 1

    if normalized_page < 1:
        return 1

    return min(normalized_page, total_pages)
