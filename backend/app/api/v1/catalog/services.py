from django.db import IntegrityError, transaction

from app.api.v1.catalog.models import Product, Stock
from app.api.v1.catalog.exceptions import (
    InvalidProductDataError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)


SUPPORTED_CURRENCIES = {"EUR"}


def create_product(
        *,
        product_sku: str,
        title: str,
        price_cents: int,
        currency: str = "EUR",
        is_active: bool = True,
        available: int = 0,
) -> Product:
    normalized_sku = _normalize_sku(product_sku)
    normalized_title = title.strip()

    if not normalized_title:
        raise InvalidProductDataError("Title товара не может быть пустым.")

    if price_cents <= 0:
        raise InvalidProductDataError("Цена товара должна быть больше нуля.")

    if available < 0:
        raise InvalidProductDataError("Количество товара не может быть отрицательным.")

    if currency not in SUPPORTED_CURRENCIES:
        raise InvalidProductDataError(f"Неподдерживаемая валюта: {currency}.")

    try:
        with transaction.atomic():
            product = Product.objects.create(
                sku=normalized_sku,
                title=title,
                price_cents=price_cents,
                currency=currency,
                is_active=is_active,
            )
            Stock.objects.create(
                product=product,
                available=available,
            )

            return (
                Product.objects
                .select_related("stock")
                .get(pk=product.pk)
            )
    except IntegrityError as e:
        raise ProductAlreadyExistsError(
            f"Товар с подобным sku='{product_sku}' уже существует."
        ) from e


def set_stock(
        *,
        product_sku: str,
        available: int,
) -> Product:
    normalized_sku = _normalize_sku(product_sku)

    if available < 0:
        raise InvalidProductDataError("Количество товара не может быть отрицательным.")

    with transaction.atomic():
        product = (
            Product.objects
            .select_for_update()
            .filter(sku=normalized_sku)
            .first()
        )

        if product is None:
            raise ProductNotFoundError(
                f"Товар с подобным sku='{product_sku}' не найден."
            )

        stock, _ = Stock.objects.get_or_create(
            product=product,
            defaults={"available": 0},
        )

        stock.available = available
        stock.save(update_fields=["available"])

        return (
            Product.objects
            .select_related("stock")
            .get(pk=product.pk)
        )


def _normalize_sku(sku: str) -> str:
    normalized_sku = sku.strip().upper()
    if not normalized_sku:
        raise InvalidProductDataError("Sku товара не может быть пустым.")

    return normalized_sku
