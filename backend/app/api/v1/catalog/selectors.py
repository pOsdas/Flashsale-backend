from dataclasses import dataclass

from django.db.models import QuerySet

from app.api.v1.catalog.exceptions import ProductNotFoundError
from app.api.v1.catalog.models import Product


@dataclass(frozen=True, slots=True)
class ProductListFilters:
    is_active: bool | None = True
    search: str | None = None


@dataclass(frozen=True, slots=True)
class Pagination:
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Limit должен быть больше 0.")
        if self.limit > 100:
            raise ValueError("Limit не может быть больше 100.")
        if self.offset < 0:
            raise ValueError("Offset не может быть отрицательным.")


def list_products(
        *,
        filters: ProductListFilters | None = None,
        pagination: Pagination | None = None
) -> QuerySet[Product]:
    filters = filters or ProductListFilters()
    pagination = pagination or Pagination()

    queryset = Product.objects.select_related("stock").all()

    if filters.is_active is not None:
        queryset = queryset.filter(is_active=filters.is_active)

    if filters.search is not None:
        queryset = queryset.filter(title__icontains=filters.search.strip())

    queryset = queryset.order_by("id")

    return queryset[pagination.offset:pagination.offset + pagination.limit]


def get_product_by_sku(
        *,
        product_sku: str,
        only_active: bool = True
) -> Product:
    queryset = Product.objects.select_related("stock").all()

    if only_active:
        queryset = queryset.filter(is_active=True)

    try:
        return queryset.get(sku=product_sku)
    except Product.DoesNotExist:
        raise ProductNotFoundError(
            f"Product with sku='{product_sku}' was not found."
        )


def get_product_by_id(
    *,
    product_id: int,
    only_active: bool = True,
) -> Product:
    queryset = Product.objects.select_related("stock").all()

    if only_active:
        queryset = queryset.filter(is_active=True)

    try:
        return queryset.get(id=product_id)
    except Product.DoesNotExist:
        raise ProductNotFoundError(
            f"Product with id={product_id} was not found."
        )