from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from app.api.v1.monitoring.models import (
    Alert,
    AlertRule,
    AlertType,
    MonitoringTarget,
    ProductSnapshot,
)
from app.api.v1.monitoring.services.alert_rule_constants import (
    ALERT_RULE_SOURCE_DEFAULT,
    ALERT_RULE_SOURCE_GLOBAL,
    ALERT_RULE_SOURCE_TARGET,
    MAX_ALERT_RULE_COOLDOWN_MINUTES,
    NUMERIC_ALERT_TYPES,
    SUPPORTED_TARGET_ALERT_TYPES,
)
from app.api.v1.monitoring.services.change_detector import (
    AlertCandidate,
)


class AlertRuleSettingsError(Exception):
    """Base alert rule settings error."""


class AlertRuleTargetNotFoundError(
    AlertRuleSettingsError,
):
    """Monitoring target does not exist or belongs to another user."""


class AlertRuleSettingsValidationError(
    AlertRuleSettingsError,
):
    """Alert rule settings payload is invalid."""


@dataclass(frozen=True, slots=True)
class AlertRuleDefaults:
    threshold_percent: Decimal | None
    threshold_absolute: Decimal | None
    cooldown_minutes: int
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class EffectiveAlertRule:
    alert_type: str
    threshold_percent: Decimal | None
    threshold_absolute: Decimal | None
    cooldown_minutes: int
    is_enabled: bool
    is_custom: bool
    source: str


@dataclass(frozen=True, slots=True)
class AlertRuleDecision:
    allowed: bool
    reason: str
    rule: EffectiveAlertRule


DEFAULT_ALERT_RULES: dict[str, AlertRuleDefaults] = {
    AlertType.PRICE_DROPPED: AlertRuleDefaults(
        threshold_percent=Decimal("5.00"),
        threshold_absolute=None,
        cooldown_minutes=360,
    ),
    AlertType.PRICE_INCREASED: AlertRuleDefaults(
        threshold_percent=Decimal("5.00"),
        threshold_absolute=None,
        cooldown_minutes=360,
    ),
    AlertType.BECAME_AVAILABLE: AlertRuleDefaults(
        threshold_percent=None,
        threshold_absolute=None,
        cooldown_minutes=360,
    ),
    AlertType.BECAME_UNAVAILABLE: AlertRuleDefaults(
        threshold_percent=None,
        threshold_absolute=None,
        cooldown_minutes=360,
    ),
    AlertType.RATING_CHANGED: AlertRuleDefaults(
        threshold_percent=None,
        threshold_absolute=Decimal("0.10"),
        cooldown_minutes=360,
    ),
    AlertType.REVIEWS_COUNT_CHANGED: AlertRuleDefaults(
        threshold_percent=None,
        threshold_absolute=Decimal("10.00"),
        cooldown_minutes=360,
    ),
    AlertType.TITLE_CHANGED: AlertRuleDefaults(
        threshold_percent=None,
        threshold_absolute=None,
        cooldown_minutes=360,
    ),
}


def get_default_alert_rule(
    *,
    alert_type: str,
) -> AlertRuleDefaults:
    try:
        return DEFAULT_ALERT_RULES[alert_type]

    except KeyError as exc:
        raise ValueError(
            f"Unsupported target alert type: {alert_type}."
        ) from exc


def get_effective_alert_rule(
    *,
    target: MonitoringTarget,
    alert_type: str,
) -> EffectiveAlertRule:
    defaults = get_default_alert_rule(
        alert_type=alert_type,
    )

    target_rule = (
        AlertRule.objects
        .filter(
            target=target,
            alert_type=alert_type,
        )
        .first()
    )

    if target_rule is not None:
        return _build_effective_rule_from_model(
            rule=target_rule,
            source=ALERT_RULE_SOURCE_TARGET,
        )

    global_rule = (
        AlertRule.objects
        .filter(
            user=target.user,
            target__isnull=True,
            alert_type=alert_type,
        )
        .first()
    )

    if global_rule is not None:
        return _build_effective_rule_from_model(
            rule=global_rule,
            source=ALERT_RULE_SOURCE_GLOBAL,
        )

    return _build_effective_rule_from_defaults(
        alert_type=alert_type,
        defaults=defaults,
    )


def get_target_alert_settings(
    *,
    user,
    target_id: UUID | str,
) -> tuple[MonitoringTarget, list[EffectiveAlertRule]]:
    target = _get_target_for_user(
        user=user,
        target_id=target_id,
    )

    rules = _build_effective_rules_for_target(
        target=target,
    )

    return target, rules


def replace_target_alert_settings(
    *,
    user,
    target_id: UUID | str,
    rules_data: list[dict[str, Any]],
) -> tuple[MonitoringTarget, list[EffectiveAlertRule]]:
    """
    Replace all target-specific alert settings.

    The request must contain exactly one rule for every supported target
    alert type. Existing target rules are updated and missing target rules
    are created.

    Global rules are not modified.
    """

    normalized_rules = _validate_and_normalize_rules_data(
        rules_data=rules_data,
    )

    with transaction.atomic():
        try:
            target = (
                MonitoringTarget.objects
                .select_for_update()
                .select_related("user")
                .get(
                    id=target_id,
                    user=user,
                )
            )

        except MonitoringTarget.DoesNotExist as exc:
            raise AlertRuleTargetNotFoundError(
                "Monitoring target was not found."
            ) from exc

        for rule_data in normalized_rules:
            AlertRule.objects.update_or_create(
                target=target,
                alert_type=rule_data["alert_type"],
                defaults={
                    "user": user,
                    "threshold_percent": (
                        rule_data["threshold_percent"]
                    ),
                    "threshold_absolute": (
                        rule_data["threshold_absolute"]
                    ),
                    "cooldown_minutes": (
                        rule_data["cooldown_minutes"]
                    ),
                    "is_enabled": rule_data["is_enabled"],
                },
            )

    rules = _build_effective_rules_for_target(
        target=target,
    )

    return target, rules


def evaluate_alert_candidate(
    *,
    snapshot: ProductSnapshot,
    candidate: AlertCandidate,
) -> AlertRuleDecision:
    if candidate.alert_type not in SUPPORTED_TARGET_ALERT_TYPES:
        fallback_rule = EffectiveAlertRule(
            alert_type=candidate.alert_type,
            threshold_percent=None,
            threshold_absolute=None,
            cooldown_minutes=0,
            is_enabled=False,
            is_custom=False,
            source=ALERT_RULE_SOURCE_DEFAULT,
        )

        return AlertRuleDecision(
            allowed=False,
            reason="unsupported_alert_type",
            rule=fallback_rule,
        )

    rule = get_effective_alert_rule(
        target=snapshot.target,
        alert_type=candidate.alert_type,
    )

    if not rule.is_enabled:
        return AlertRuleDecision(
            allowed=False,
            reason="rule_disabled",
            rule=rule,
        )

    if rule.threshold_percent is not None:
        if candidate.change_percent is None:
            return AlertRuleDecision(
                allowed=False,
                reason="percent_change_unavailable",
                rule=rule,
            )

        if candidate.change_percent < rule.threshold_percent:
            return AlertRuleDecision(
                allowed=False,
                reason="percent_threshold_not_reached",
                rule=rule,
            )

    if rule.threshold_absolute is not None:
        if candidate.change_absolute is None:
            return AlertRuleDecision(
                allowed=False,
                reason="absolute_change_unavailable",
                rule=rule,
            )

        if candidate.change_absolute < rule.threshold_absolute:
            return AlertRuleDecision(
                allowed=False,
                reason="absolute_threshold_not_reached",
                rule=rule,
            )

    if _is_alert_in_cooldown(
        snapshot=snapshot,
        alert_type=candidate.alert_type,
        cooldown_minutes=rule.cooldown_minutes,
    ):
        return AlertRuleDecision(
            allowed=False,
            reason="cooldown_active",
            rule=rule,
        )

    return AlertRuleDecision(
        allowed=True,
        reason="allowed",
        rule=rule,
    )


def _get_target_for_user(
    *,
    user,
    target_id: UUID | str,
) -> MonitoringTarget:
    try:
        return (
            MonitoringTarget.objects
            .select_related("user")
            .get(
                id=target_id,
                user=user,
            )
        )

    except MonitoringTarget.DoesNotExist as exc:
        raise AlertRuleTargetNotFoundError(
            "Monitoring target was not found."
        ) from exc


def _build_effective_rules_for_target(
    *,
    target: MonitoringTarget,
) -> list[EffectiveAlertRule]:
    target_rules = {
        rule.alert_type: rule
        for rule in (
            AlertRule.objects
            .filter(
                target=target,
                alert_type__in=SUPPORTED_TARGET_ALERT_TYPES,
            )
        )
    }

    global_rules = {
        rule.alert_type: rule
        for rule in (
            AlertRule.objects
            .filter(
                user=target.user,
                target__isnull=True,
                alert_type__in=SUPPORTED_TARGET_ALERT_TYPES,
            )
        )
    }

    effective_rules: list[EffectiveAlertRule] = []

    for alert_type in SUPPORTED_TARGET_ALERT_TYPES:
        target_rule = target_rules.get(alert_type)

        if target_rule is not None:
            effective_rules.append(
                _build_effective_rule_from_model(
                    rule=target_rule,
                    source=ALERT_RULE_SOURCE_TARGET,
                )
            )
            continue

        global_rule = global_rules.get(alert_type)

        if global_rule is not None:
            effective_rules.append(
                _build_effective_rule_from_model(
                    rule=global_rule,
                    source=ALERT_RULE_SOURCE_GLOBAL,
                )
            )
            continue

        effective_rules.append(
            _build_effective_rule_from_defaults(
                alert_type=alert_type,
                defaults=get_default_alert_rule(
                    alert_type=alert_type,
                ),
            )
        )

    return effective_rules


def _build_effective_rule_from_model(
    *,
    rule: AlertRule,
    source: str,
) -> EffectiveAlertRule:
    return EffectiveAlertRule(
        alert_type=rule.alert_type,
        threshold_percent=rule.threshold_percent,
        threshold_absolute=rule.threshold_absolute,
        cooldown_minutes=rule.cooldown_minutes,
        is_enabled=rule.is_enabled,
        is_custom=True,
        source=source,
    )


def _build_effective_rule_from_defaults(
    *,
    alert_type: str,
    defaults: AlertRuleDefaults,
) -> EffectiveAlertRule:
    return EffectiveAlertRule(
        alert_type=alert_type,
        threshold_percent=defaults.threshold_percent,
        threshold_absolute=defaults.threshold_absolute,
        cooldown_minutes=defaults.cooldown_minutes,
        is_enabled=defaults.is_enabled,
        is_custom=False,
        source=ALERT_RULE_SOURCE_DEFAULT,
    )


def _validate_and_normalize_rules_data(
    *,
    rules_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(rules_data, list):
        raise AlertRuleSettingsValidationError(
            "Rules must be provided as a list."
        )

    received_types: list[str] = []

    for rule_data in rules_data:
        if not isinstance(rule_data, dict):
            raise AlertRuleSettingsValidationError(
                "Every alert rule must be an object."
            )

        alert_type = rule_data.get("alert_type")

        if not alert_type:
            raise AlertRuleSettingsValidationError(
                "Every alert rule must contain alert_type."
            )

        received_types.append(str(alert_type))

    duplicate_types = {
        alert_type
        for alert_type in received_types
        if received_types.count(alert_type) > 1
    }

    if duplicate_types:
        raise AlertRuleSettingsValidationError(
            "Duplicate alert rule types: "
            f"{', '.join(sorted(duplicate_types))}."
        )

    received_type_set = set(received_types)
    supported_type_set = set(
        SUPPORTED_TARGET_ALERT_TYPES
    )

    missing_types = (
        supported_type_set - received_type_set
    )
    unsupported_types = (
        received_type_set - supported_type_set
    )

    if missing_types:
        raise AlertRuleSettingsValidationError(
            "Missing alert rule types: "
            f"{', '.join(sorted(missing_types))}."
        )

    if unsupported_types:
        raise AlertRuleSettingsValidationError(
            "Unsupported alert rule types: "
            f"{', '.join(sorted(unsupported_types))}."
        )

    normalized_rules: list[dict[str, Any]] = []

    for rule_data in rules_data:
        alert_type = str(
            rule_data["alert_type"]
        )

        threshold_percent = (
            _to_non_negative_decimal_or_none(
                value=rule_data.get(
                    "threshold_percent"
                ),
                field_name="threshold_percent",
            )
        )
        threshold_absolute = (
            _to_non_negative_decimal_or_none(
                value=rule_data.get(
                    "threshold_absolute"
                ),
                field_name="threshold_absolute",
            )
        )

        try:
            cooldown_minutes = int(
                rule_data["cooldown_minutes"]
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise AlertRuleSettingsValidationError(
                "cooldown_minutes must be an integer."
            ) from exc

        if cooldown_minutes < 0:
            raise AlertRuleSettingsValidationError(
                "cooldown_minutes cannot be negative."
            )

        if (
            cooldown_minutes
            > MAX_ALERT_RULE_COOLDOWN_MINUTES
        ):
            raise AlertRuleSettingsValidationError(
                "cooldown_minutes cannot be greater than "
                f"{MAX_ALERT_RULE_COOLDOWN_MINUTES}."
            )

        if alert_type not in NUMERIC_ALERT_TYPES:
            if (
                threshold_percent is not None
                or threshold_absolute is not None
            ):
                raise AlertRuleSettingsValidationError(
                    "Thresholds are not supported for alert type "
                    f"{alert_type}."
                )

        if "is_enabled" not in rule_data:
            raise AlertRuleSettingsValidationError(
                "Every alert rule must contain is_enabled."
            )

        is_enabled = rule_data["is_enabled"]

        if not isinstance(is_enabled, bool):
            raise AlertRuleSettingsValidationError(
                "is_enabled must be a boolean."
            )

        normalized_rules.append(
            {
                "alert_type": alert_type,
                "threshold_percent": threshold_percent,
                "threshold_absolute": threshold_absolute,
                "cooldown_minutes": cooldown_minutes,
                "is_enabled": is_enabled,
            }
        )

    normalized_rules.sort(
        key=lambda item: (
            SUPPORTED_TARGET_ALERT_TYPES.index(
                item["alert_type"]
            )
        )
    )

    return normalized_rules


def _to_non_negative_decimal_or_none(
    *,
    value: Any,
    field_name: str,
) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        decimal_value = Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise AlertRuleSettingsValidationError(
            f"{field_name} must be a decimal number or null."
        ) from exc

    if decimal_value < 0:
        raise AlertRuleSettingsValidationError(
            f"{field_name} cannot be negative."
        )

    return decimal_value


def _is_alert_in_cooldown(
    *,
    snapshot: ProductSnapshot,
    alert_type: str,
    cooldown_minutes: int,
) -> bool:
    if cooldown_minutes <= 0:
        return False

    cooldown_started_at = (
        timezone.now()
        - timedelta(minutes=cooldown_minutes)
    )

    return (
        Alert.objects
        .filter(
            target=snapshot.target,
            alert_type=alert_type,
            created_at__gte=cooldown_started_at,
        )
        .exists()
    )
