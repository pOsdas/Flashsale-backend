from decimal import Decimal

from app.api.v1.monitoring.models import (
    AlertType,
    MonitoringTarget,
)
from app.api.v1.monitoring.services.alert_rule_service import (
    EffectiveAlertRule,
)
from app.api.v1.notifications.telegram.target_alert_rule_options import (
    get_threshold_kind,
)


ALERT_TYPE_TITLES: dict[str, str] = {
    AlertType.PRICE_DROPPED: "Снижение цены",
    AlertType.PRICE_INCREASED: "Рост цены",
    AlertType.BECAME_AVAILABLE: "Появление в наличии",
    AlertType.BECAME_UNAVAILABLE: "Исчезновение из наличия",
    AlertType.RATING_CHANGED: "Изменение рейтинга",
    AlertType.REVIEWS_COUNT_CHANGED: "Изменение отзывов",
    AlertType.TITLE_CHANGED: "Изменение названия",
}

ALERT_TYPE_TO_CALLBACK_CODE: dict[str, str] = {
    AlertType.PRICE_DROPPED: "pd",
    AlertType.PRICE_INCREASED: "pi",
    AlertType.BECAME_AVAILABLE: "ba",
    AlertType.BECAME_UNAVAILABLE: "bu",
    AlertType.RATING_CHANGED: "rt",
    AlertType.REVIEWS_COUNT_CHANGED: "rv",
    AlertType.TITLE_CHANGED: "tt",
}

CALLBACK_CODE_TO_ALERT_TYPE: dict[str, str] = {
    code: alert_type
    for alert_type, code in ALERT_TYPE_TO_CALLBACK_CODE.items()
}


def build_target_alert_settings_text(
    *,
    target: MonitoringTarget,
    rules: list[EffectiveAlertRule] | tuple[EffectiveAlertRule, ...],
) -> str:
    title = target.title or target.external_id or target.url
    lines = [
        "🔔 Настройки уведомлений",
        "",
        title,
        "",
        "Нажмите название правила, чтобы включить или выключить его.",
        "Кнопка ⚙️ открывает настройку порога и периода тишины.",
        "",
    ]

    for rule in rules:
        state = "✅" if rule.is_enabled else "❌"
        rule_title = ALERT_TYPE_TITLES.get(
            rule.alert_type,
            rule.alert_type,
        )
        details = format_rule_details(rule)
        lines.append(f"{state} {rule_title}{details}")

    return "\n".join(lines).strip()


def build_target_alert_rule_detail_text(
    *,
    target: MonitoringTarget,
    rule: EffectiveAlertRule,
) -> str:
    target_title = target.title or target.external_id or target.url
    rule_title = ALERT_TYPE_TITLES.get(
        rule.alert_type,
        rule.alert_type,
    )
    state = "включено" if rule.is_enabled else "выключено"
    threshold_kind = get_threshold_kind(alert_type=rule.alert_type)

    lines = [
        "⚙️ Настройка уведомления",
        "",
        target_title,
        "",
        f"Правило: {rule_title}",
        f"Состояние: {state}",
    ]

    if threshold_kind is None:
        lines.append("Порог: не используется")
    else:
        lines.append(f"Порог: {format_rule_threshold(rule)}")

    lines.extend(
        [
            f"Период тишины: {format_minutes(rule.cooldown_minutes)}",
            "",
        ]
    )

    if threshold_kind == "percent":
        lines.append(
            "Порог определяет минимальное изменение цены в процентах, "
            "после которого создаётся уведомление."
        )
    elif rule.alert_type == AlertType.RATING_CHANGED:
        lines.append(
            "Порог определяет минимальное изменение рейтинга."
        )
    elif rule.alert_type == AlertType.REVIEWS_COUNT_CHANGED:
        lines.append(
            "Порог определяет минимальное изменение количества отзывов."
        )
    else:
        lines.append(
            "Для этого события уведомление создаётся при самом факте изменения."
        )

    lines.append(
        "Период тишины запрещает повторное уведомление того же типа "
        "для этого товара до истечения выбранного времени."
    )

    return "\n".join(lines).strip()


def format_rule_details(rule: EffectiveAlertRule) -> str:
    details: list[str] = []

    if (
        rule.threshold_percent is not None
        or rule.threshold_absolute is not None
    ):
        details.append(f"порог {format_rule_threshold(rule)}")

    details.append(f"тишина {format_minutes(rule.cooldown_minutes)}")

    return " · " + " · ".join(details)


def format_rule_threshold(rule: EffectiveAlertRule) -> str:
    if rule.threshold_percent is not None:
        return f"{format_decimal(rule.threshold_percent)}%"

    if rule.threshold_absolute is not None:
        return format_decimal(rule.threshold_absolute)

    return "не задан"


def format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def format_minutes(minutes: int) -> str:
    if minutes == 0:
        return "без паузы"

    if minutes % 1440 == 0:
        days = minutes // 1440

        if days == 1:
            return "1 день"

        if 2 <= days <= 4:
            return f"{days} дня"

        return f"{days} дней"

    if minutes % 60 == 0:
        hours = minutes // 60

        if hours == 1:
            return "1 час"

        if 2 <= hours <= 4:
            return f"{hours} часа"

        return f"{hours} часов"

    return f"{minutes} мин."
