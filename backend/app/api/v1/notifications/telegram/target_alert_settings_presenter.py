from decimal import Decimal

from app.api.v1.monitoring.models import (
    AlertType,
    MonitoringTarget,
)
from app.api.v1.monitoring.services.alert_rule_service import (
    EffectiveAlertRule,
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
        "Нажмите правило, чтобы включить или выключить его.",
        "Порог и период тишины пока используются из текущих настроек.",
        "",
    ]

    for rule in rules:
        state = "✅" if rule.is_enabled else "❌"
        rule_title = ALERT_TYPE_TITLES.get(
            rule.alert_type,
            rule.alert_type,
        )
        details = _format_rule_details(rule)
        lines.append(f"{state} {rule_title}{details}")

    return "\n".join(lines).strip()


def _format_rule_details(rule: EffectiveAlertRule) -> str:
    details: list[str] = []

    if rule.threshold_percent is not None:
        details.append(
            f"порог {_format_decimal(rule.threshold_percent)}%"
        )

    if rule.threshold_absolute is not None:
        details.append(
            f"порог {_format_decimal(rule.threshold_absolute)}"
        )

    if rule.cooldown_minutes > 0:
        details.append(
            f"пауза {_format_minutes(rule.cooldown_minutes)}"
        )

    if not details:
        return ""

    return " · " + " · ".join(details)


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


def _format_minutes(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} дн."

    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} ч."

    return f"{minutes} мин."
