from django.db import IntegrityError, transaction

from app.core.logging import get_logger
from app.api.v1.catalog.models import Product, Stock
from app.api.v1.catalog.exceptions import (
    InvalidProductDataError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
)

logger = get_logger(__name__)

SUPPORTED_CURRENCIES = {"EUR", "RUB"}


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
        logger.error(
            "Invalid product title",
            extra={
                "product_sku": product_sku,
                "title": title,
            },
        )
        raise InvalidProductDataError("Title товара не может быть пустым.")

    if price_cents <= 0:
        logger.error(
            "Invalid product price",
            extra={
                "product_sku": product_sku,
                "price_cents": price_cents,
            },
        )
        raise InvalidProductDataError("Цена товара должна быть больше нуля.")

    if available < 0:
        logger.error(
            "Invalid product stock amount",
            extra={
                "product_sku": product_sku,
                "available": available,
            },
        )
        raise InvalidProductDataError("Количество товара не может быть отрицательным.")

    if currency not in SUPPORTED_CURRENCIES:
        logger.error(
            "Unsupported currency",
            extra={
                "product_sku": product_sku,
                "currency": currency,
            },
        )
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
        logger.error(
            "Product creation failed due to integrity error",
            extra={
                "product_sku": product_sku,
                "normalized_sku": normalized_sku,
                "title": title,
                "price_cents": price_cents,
                "currency": currency,
                "available": available,
            },
            exc_info=True,
        )
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
        logger.error(
            "Invalid stock value",
            extra={
                "product_sku": product_sku,
                "available": available,
            },
        )
        raise InvalidProductDataError("Количество товара не может быть отрицательным.")

    with transaction.atomic():
        product = (
            Product.objects
            .select_for_update()
            .filter(sku=normalized_sku)
            .first()
        )

        if product is None:
            logger.error(
                "Product not found while setting stock",
                extra={
                    "product_sku": product_sku,
                    "normalized_sku": normalized_sku,
                },
            )
            raise ProductNotFoundError(
                f"Товар с подобным sku='{product_sku}' не найден."
            )

        try:
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
        except Exception as e:
            logger.error(
                "Failed to set stock",
                extra={
                    "product_sku": product_sku,
                    "normalized_sku": normalized_sku,
                    "available": available,
                    "product_id": product.id,
                },
                exc_info=True,
            )
            raise


def _normalize_sku(sku: str) -> str:
    normalized_sku = sku.strip().upper()
    if not normalized_sku:
        logger.error(
            "Invalid SKU normalization",
            extra={
                "sku": sku,
            },
        )
        raise InvalidProductDataError("Sku товара не может быть пустым.")

    return normalized_sku
