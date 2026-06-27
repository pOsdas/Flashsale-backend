from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.api.v1.monitoring.models import AlertType


ThresholdKind = Literal["percent", "absolute"]


@dataclass(frozen=True, slots=True)
class AlertThresholdOption:
    code: str
    value: Decimal
    label: str


@dataclass(frozen=True, slots=True)
class AlertCooldownOption:
    minutes: int
    label: str


PRICE_THRESHOLD_OPTIONS: tuple[AlertThresholdOption, ...] = (
    AlertThresholdOption("1", Decimal("1.00"), "1%"),
    AlertThresholdOption("3", Decimal("3.00"), "3%"),
    AlertThresholdOption("5", Decimal("5.00"), "5%"),
    AlertThresholdOption("10", Decimal("10.00"), "10%"),
    AlertThresholdOption("20", Decimal("20.00"), "20%"),
)

RATING_THRESHOLD_OPTIONS: tuple[AlertThresholdOption, ...] = (
    AlertThresholdOption("01", Decimal("0.10"), "0.1"),
    AlertThresholdOption("02", Decimal("0.20"), "0.2"),
    AlertThresholdOption("05", Decimal("0.50"), "0.5"),
    AlertThresholdOption("1", Decimal("1.00"), "1.0"),
)

REVIEWS_THRESHOLD_OPTIONS: tuple[AlertThresholdOption, ...] = (
    AlertThresholdOption("1", Decimal("1.00"), "1"),
    AlertThresholdOption("5", Decimal("5.00"), "5"),
    AlertThresholdOption("10", Decimal("10.00"), "10"),
    AlertThresholdOption("25", Decimal("25.00"), "25"),
    AlertThresholdOption("50", Decimal("50.00"), "50"),
    AlertThresholdOption("100", Decimal("100.00"), "100"),
)

ALERT_COOLDOWN_OPTIONS: tuple[AlertCooldownOption, ...] = (
    AlertCooldownOption(0, "Без паузы"),
    AlertCooldownOption(60, "1 час"),
    AlertCooldownOption(180, "3 часа"),
    AlertCooldownOption(360, "6 часов"),
    AlertCooldownOption(720, "12 часов"),
    AlertCooldownOption(1440, "1 день"),
    AlertCooldownOption(4320, "3 дня"),
    AlertCooldownOption(10080, "7 дней"),
)


def get_threshold_kind(*, alert_type: str) -> ThresholdKind | None:
    if alert_type in {
        AlertType.PRICE_DROPPED,
        AlertType.PRICE_INCREASED,
    }:
        return "percent"

    if alert_type in {
        AlertType.RATING_CHANGED,
        AlertType.REVIEWS_COUNT_CHANGED,
    }:
        return "absolute"

    return None


def get_threshold_options(
    *,
    alert_type: str,
) -> tuple[AlertThresholdOption, ...]:
    if alert_type in {
        AlertType.PRICE_DROPPED,
        AlertType.PRICE_INCREASED,
    }:
        return PRICE_THRESHOLD_OPTIONS

    if alert_type == AlertType.RATING_CHANGED:
        return RATING_THRESHOLD_OPTIONS

    if alert_type == AlertType.REVIEWS_COUNT_CHANGED:
        return REVIEWS_THRESHOLD_OPTIONS

    return ()


def get_threshold_option_by_code(
    *,
    alert_type: str,
    code: str,
) -> AlertThresholdOption | None:
    return next(
        (
            option
            for option in get_threshold_options(alert_type=alert_type)
            if option.code == code
        ),
        None,
    )


def get_cooldown_option_by_minutes(
    *,
    minutes: int,
) -> AlertCooldownOption | None:
    return next(
        (
            option
            for option in ALERT_COOLDOWN_OPTIONS
            if option.minutes == minutes
        ),
        None,
    )
