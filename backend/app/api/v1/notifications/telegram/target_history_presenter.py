from datetime import datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from app.api.v1.monitoring.models import (
    Alert,
    AlertType,
    Marketplace,
    ProductSnapshot,
    SnapshotParseStatus,
)
from app.api.v1.monitoring.services.target_history_service import (
    MonitoringTargetHistory,
)


ALERT_TITLES: dict[str, str] = {
    AlertType.PRICE_DROPPED: "Цена снизилась",
    AlertType.PRICE_INCREASED: "Цена выросла",
    AlertType.BECAME_AVAILABLE: "Товар появился в наличии",
    AlertType.BECAME_UNAVAILABLE: "Товар пропал из наличия",
    AlertType.RATING_CHANGED: "Рейтинг изменился",
    AlertType.REVIEWS_COUNT_CHANGED: "Количество отзывов изменилось",
    AlertType.TITLE_CHANGED: "Название изменилось",
}

MARKETPLACE_TITLES = {
    Marketplace.WILDBERRIES: "Wildberries",
    Marketplace.OZON: "Ozon",
}


def build_target_history_text(
    *,
    history: MonitoringTargetHistory,
) -> str:
    target = history.target
    title = target.title or target.external_id or target.url
    marketplace = MARKETPLACE_TITLES.get(
        target.marketplace,
        target.marketplace.upper(),
    )
    lines = [
        "📜 История товара",
        "",
        _truncate(title, 180),
        marketplace,
        "",
        "Последние проверки:",
    ]

    if history.snapshots:
        for index, snapshot in enumerate(history.snapshots, start=1):
            lines.append(
                _format_snapshot_line(
                    index=index,
                    snapshot=snapshot,
                )
            )
    else:
        lines.append("Проверок пока нет.")

    lines.extend(
        [
            "",
            "Последние изменения:",
        ]
    )

    if history.alerts:
        for index, alert in enumerate(history.alerts, start=1):
            lines.extend(
                _format_alert_lines(
                    index=index,
                    alert=alert,
                )
            )
    else:
        lines.append("Изменений пока не обнаружено.")

    return "\n".join(lines).strip()


def _format_snapshot_line(
    *,
    index: int,
    snapshot: ProductSnapshot,
) -> str:
    checked_at = _format_datetime(snapshot.checked_at)

    if snapshot.parse_status != SnapshotParseStatus.SUCCESS:
        status = _format_parse_status(snapshot.parse_status)
        return f"{index}. {checked_at} · {status}"

    price = _format_price(snapshot.price, snapshot.currency)
    availability = _format_availability(snapshot.is_available)
    return f"{index}. {checked_at} · {price} · {availability}"


def _format_alert_lines(
    *,
    index: int,
    alert: Alert,
) -> list[str]:
    title = ALERT_TITLES.get(
        alert.alert_type,
        alert.title or alert.alert_type,
    )
    created_at = _format_datetime(alert.created_at)
    lines = [
        f"{index}. {created_at} · {_truncate(title, 90)}",
    ]

    value_change = _format_alert_value_change(alert)

    if value_change:
        lines.append(f"   {value_change}")
    elif alert.message:
        lines.append(f"   {_truncate(alert.message, 140)}")

    return lines


def _format_alert_value_change(alert: Alert) -> str:
    old_value = _format_alert_value(
        alert_type=alert.alert_type,
        value=alert.old_value,
    )
    new_value = _format_alert_value(
        alert_type=alert.alert_type,
        value=alert.new_value,
    )

    if old_value is None and new_value is None:
        return ""

    return f"{old_value or '—'} → {new_value or '—'}"


def _format_alert_value(
    *,
    alert_type: str,
    value: Any,
) -> str | None:
    if value in (None, ""):
        return None

    if alert_type in {
        AlertType.PRICE_DROPPED,
        AlertType.PRICE_INCREASED,
    }:
        return _format_price(value, "RUB")

    if alert_type in {
        AlertType.BECAME_AVAILABLE,
        AlertType.BECAME_UNAVAILABLE,
    }:
        return _format_availability(_to_bool_or_none(value))

    if isinstance(value, dict):
        if "value" in value:
            return _truncate(str(value["value"]), 80)
        return _truncate(str(value), 80)

    return _truncate(str(value), 80)


def _format_price(value: Any, currency: str) -> str:
    if value is None:
        return "цена неизвестна"

    try:
        decimal_value = Decimal(str(value))
    except Exception:
        return _truncate(str(value), 80)

    if decimal_value == decimal_value.to_integral_value():
        formatted = f"{int(decimal_value):,}".replace(",", " ")
    else:
        formatted = f"{decimal_value:,.2f}".replace(",", " ")

    if (currency or "RUB").upper() == "RUB":
        return f"{formatted} ₽"

    return f"{formatted} {(currency or 'RUB').upper()}"


def _format_availability(value: bool | None) -> str:
    if value is True:
        return "в наличии"

    if value is False:
        return "нет в наличии"

    return "наличие неизвестно"


def _format_parse_status(parse_status: str) -> str:
    titles = {
        SnapshotParseStatus.NOT_FOUND: "товар не найден",
        SnapshotParseStatus.BLOCKED: "запрос заблокирован",
        SnapshotParseStatus.PARSE_ERROR: "ошибка парсинга",
        SnapshotParseStatus.MARKETPLACE_ERROR: "ошибка маркетплейса",
    }
    return titles.get(parse_status, parse_status)


def _format_datetime(value: datetime) -> str:
    try:
        local_value = timezone.localtime(value)
    except ValueError:
        local_value = value

    return local_value.strftime("%d.%m.%Y %H:%M")


def _to_bool_or_none(value: Any) -> bool | None:
    if value in (True, "true", "True", 1, "1"):
        return True

    if value in (False, "false", "False", 0, "0"):
        return False

    return None


def _truncate(value: str, max_length: int) -> str:
    normalized = " ".join(str(value).split())

    if len(normalized) <= max_length:
        return normalized

    return normalized[:max_length - 1].rstrip() + "…"
