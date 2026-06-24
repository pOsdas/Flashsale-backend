from app.api.v1.monitoring.models import Marketplace, MonitoringTarget
from app.api.v1.monitoring.services.product_preview import ProductPreviewData
from app.api.v1.notifications.telegram.pending_product import (
    PendingTelegramProduct,
)


MARKETPLACE_TITLES = {
    Marketplace.WILDBERRIES: "Wildberries",
    Marketplace.OZON: "Ozon",
}


def build_product_preview_text(
    *,
    marketplace: str,
    preview: ProductPreviewData,
) -> str:
    lines = [
        "🔎 Найден товар",
        "",
        preview.title,
        "",
        f"Маркетплейс: {_format_marketplace(marketplace)}",
        f"Цена: {_format_price(preview.price, preview.currency)}",
    ]

    if (
        preview.old_price is not None
        and preview.old_price != preview.price
    ):
        lines.append(
            "Старая цена: "
            f"{_format_price(preview.old_price, preview.currency)}"
        )

    lines.append(
        "Наличие: "
        + ("в наличии" if preview.is_available else "нет в наличии")
    )

    if preview.rating is not None:
        lines.append(f"Рейтинг: {preview.rating:g}")

    if preview.reviews_count is not None:
        lines.append(
            "Отзывов: "
            f"{preview.reviews_count:,}".replace(",", " ")
        )

    if preview.brand:
        lines.append(f"Бренд: {preview.brand}")

    if preview.seller_name:
        lines.append(f"Продавец: {preview.seller_name}")

    lines.extend(
        [
            "",
            "Добавить товар в отслеживание?",
        ]
    )

    return "\n".join(lines)


def build_product_added_text(
    *,
    target: MonitoringTarget,
    already_existed: bool,
) -> str:
    title = target.title or target.external_id or target.url
    status_line = (
        "ℹ️ Этот товар уже отслеживается."
        if already_existed
        else "✅ Товар добавлен в отслеживание."
    )

    return (
        f"{status_line}\n\n"
        f"{title}\n"
        f"Маркетплейс: {_format_marketplace(target.marketplace)}\n"
        f"Проверка: раз в {target.check_interval_minutes} минут\n\n"
        "Команда /products позволит управлять товарами "
        "на следующем этапе."
    )


def build_product_cancelled_text(
    *,
    pending_product: PendingTelegramProduct,
) -> str:
    return (
        "❌ Добавление отменено.\n\n"
        f"{pending_product.title}\n"
        f"Маркетплейс: "
        f"{_format_marketplace(pending_product.marketplace)}"
    )


def build_product_retry_text(
    *,
    pending_product: PendingTelegramProduct,
    error_message: str,
) -> str:
    return (
        "⚠️ Не удалось добавить товар.\n\n"
        f"{error_message}\n\n"
        f"{pending_product.title}\n"
        f"Маркетплейс: "
        f"{_format_marketplace(pending_product.marketplace)}\n\n"
        "Попробуйте ещё раз или отмените добавление."
    )


def _format_marketplace(marketplace: str) -> str:
    return MARKETPLACE_TITLES.get(
        marketplace,
        marketplace.upper(),
    )


def _format_price(
    value: int | None,
    currency: str,
) -> str:
    if value is None:
        return "не указана"

    formatted_value = f"{value:,}".replace(",", " ")
    normalized_currency = (currency or "RUB").upper()

    if normalized_currency == "RUB":
        return f"{formatted_value} ₽"

    return f"{formatted_value} {normalized_currency}"
