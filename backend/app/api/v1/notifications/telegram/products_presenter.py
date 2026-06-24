from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from app.api.v1.monitoring.models import (
    Marketplace,
    MonitoringTarget,
    MonitoringTargetStatus,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.target_query_service import (
    MonitoringTargetListItem,
    MonitoringTargetPage,
)


MARKETPLACE_TITLES = {
    Marketplace.WILDBERRIES: "Wildberries",
    Marketplace.OZON: "Ozon",
}

STATUS_TITLES = {
    MonitoringTargetStatus.ACTIVE: "активно",
    MonitoringTargetStatus.PAUSED: "приостановлено",
    MonitoringTargetStatus.FAILED: "ошибка",
}


def build_products_page_text(
    *,
    target_page: MonitoringTargetPage,
) -> str:
    if target_page.total_items == 0:
        return (
            "📦 У вас пока нет отслеживаемых товаров.\n\n"
            "Отправьте ссылку на товар Wildberries или Ozon, "
            "чтобы добавить его."
        )

    lines = [
        "📦 Отслеживаемые товары",
        "",
        (
            f"Страница {target_page.page} из "
            f"{target_page.total_pages} · "
            f"Всего: {target_page.total_items}"
        ),
        "",
    ]
    start_number = (
        (target_page.page - 1) * target_page.page_size
    )

    for index, item in enumerate(
        target_page.items,
        start=start_number + 1,
    ):
        lines.extend(
            _build_target_lines(
                index=index,
                item=item,
            )
        )
        lines.append("")

    lines.extend(
        [
            "Кнопки ниже относятся к номеру товара.",
            "⚙️ Настройки уведомлений добавим следующим этапом.",
        ]
    )

    return "\n".join(lines).strip()


def build_target_delete_confirmation_text(
    *,
    target: MonitoringTarget,
) -> str:
    title = target.title or target.external_id or target.url

    return (
        "⚠️ Удалить товар из отслеживания?\n\n"
        f"{title}\n"
        f"Маркетплейс: {_format_marketplace(target.marketplace)}\n\n"
        "Будут удалены история проверок, alerts и индивидуальные "
        "настройки этого товара. Действие нельзя отменить."
    )


def build_target_check_result_text(
    *,
    target: MonitoringTarget,
    price,
    currency: str,
    is_available: bool | None,
    alerts_count: int,
) -> str:
    title = target.title or target.external_id or target.url

    return (
        "✅ Товар проверен.\n\n"
        f"{title}\n"
        f"Цена: {_format_price(price, currency)}\n"
        f"Наличие: {_format_availability(is_available)}\n"
        f"Обнаружено изменений: {alerts_count}"
    )


def _build_target_lines(
    *,
    index: int,
    item: MonitoringTargetListItem,
) -> list[str]:
    target = item.target
    title = target.title or target.external_id or target.url
    status = _format_target_status(target)

    lines = [
        f"{index}. {title}",
        (
            f"{_format_marketplace(target.marketplace)} · "
            f"{status}"
        ),
        (
            "Цена: "
            f"{_format_price(item.latest_price, item.latest_currency)}"
        ),
        (
            "Наличие: "
            f"{_format_availability(item.latest_is_available)}"
        ),
        f"Проверка: раз в {target.check_interval_minutes} минут",
    ]

    if item.latest_checked_at is not None:
        lines.append(
            "Последняя проверка: "
            f"{_format_datetime(item.latest_checked_at)}"
        )
    else:
        lines.append("Последняя проверка: ещё не выполнялась")

    if (
        item.latest_parse_status
        and item.latest_parse_status != SnapshotParseStatus.SUCCESS
    ):
        lines.append(
            "Последний результат: "
            f"{_format_parse_status(item.latest_parse_status)}"
        )

    return lines


def _format_target_status(target: MonitoringTarget) -> str:
    status_title = STATUS_TITLES.get(
        target.status,
        target.status,
    )

    if (
        target.status == MonitoringTargetStatus.ACTIVE
        and target.is_active
    ):
        return "✅ активно"

    if target.status == MonitoringTargetStatus.PAUSED:
        return "⏸ приостановлено"

    if target.status == MonitoringTargetStatus.FAILED:
        return "⚠️ ошибка"

    return status_title


def _format_parse_status(parse_status: str) -> str:
    titles = {
        SnapshotParseStatus.NOT_FOUND: "товар не найден",
        SnapshotParseStatus.BLOCKED: "маркетплейс заблокировал запрос",
        SnapshotParseStatus.PARSE_ERROR: "ошибка парсинга",
        SnapshotParseStatus.MARKETPLACE_ERROR: "ошибка маркетплейса",
    }
    return titles.get(parse_status, parse_status)


def _format_marketplace(marketplace: str) -> str:
    return MARKETPLACE_TITLES.get(
        marketplace,
        marketplace.upper(),
    )


def _format_price(
    value: Decimal | int | None,
    currency: str,
) -> str:
    if value is None:
        return "не указана"

    try:
        decimal_value = Decimal(str(value))
    except Exception:
        return str(value)

    if decimal_value == decimal_value.to_integral_value():
        formatted_value = f"{int(decimal_value):,}".replace(",", " ")
    else:
        formatted_value = f"{decimal_value:,.2f}".replace(",", " ")

    normalized_currency = (currency or "RUB").upper()

    if normalized_currency == "RUB":
        return f"{formatted_value} ₽"

    return f"{formatted_value} {normalized_currency}"


def _format_availability(value: bool | None) -> str:
    if value is True:
        return "в наличии"

    if value is False:
        return "нет в наличии"

    return "неизвестно"


def _format_datetime(value: datetime) -> str:
    try:
        local_value = timezone.localtime(value)
    except ValueError:
        local_value = value

    return local_value.strftime("%d.%m.%Y %H:%M")
