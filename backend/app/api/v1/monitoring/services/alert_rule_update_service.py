from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.db import transaction

from app.api.v1.monitoring.models import (
    AlertRule,
    MonitoringTarget,
)
from app.api.v1.monitoring.services.alert_rule_constants import (
    MAX_ALERT_RULE_COOLDOWN_MINUTES,
    NUMERIC_ALERT_TYPES,
    SUPPORTED_TARGET_ALERT_TYPES,
)
from app.api.v1.monitoring.services.alert_rule_service import (
    AlertRuleSettingsValidationError,
    AlertRuleTargetNotFoundError,
    EffectiveAlertRule,
    get_effective_alert_rule,
)


@dataclass(frozen=True, slots=True)
class TargetAlertRuleUpdateResult:
    target: MonitoringTarget
    rule: EffectiveAlertRule
    changed: bool


def set_target_alert_rule_enabled(
    *,
    user,
    target_id: UUID | str,
    alert_type: str,
    is_enabled: bool,
) -> TargetAlertRuleUpdateResult:
    """
    Set the enabled state of one target-specific alert rule.

    If the effective rule currently comes from a global rule or application
    defaults, a target-specific rule is created with the same thresholds and
    cooldown. Only the enabled flag is changed.
    """

    if not isinstance(is_enabled, bool):
        raise AlertRuleSettingsValidationError(
            "is_enabled must be a boolean."
        )

    return _update_target_alert_rule(
        user=user,
        target_id=target_id,
        alert_type=alert_type,
        updates={
            "is_enabled": is_enabled,
        },
    )


def set_target_alert_rule_threshold(
    *,
    user,
    target_id: UUID | str,
    alert_type: str,
    threshold_percent: Decimal | int | float | str | None,
    threshold_absolute: Decimal | int | float | str | None,
) -> TargetAlertRuleUpdateResult:
    """
    Replace the threshold of one target-specific alert rule.

    A rule can use a percentage threshold or an absolute threshold. Telegram
    currently supplies exactly one of them and explicitly clears the other so
    that the alert does not unexpectedly require two thresholds at once.
    """

    _validate_alert_type(alert_type=alert_type)

    if alert_type not in NUMERIC_ALERT_TYPES:
        raise AlertRuleSettingsValidationError(
            f"Thresholds are not supported for alert type {alert_type}."
        )

    normalized_percent = _to_non_negative_decimal_or_none(
        value=threshold_percent,
        field_name="threshold_percent",
    )
    normalized_absolute = _to_non_negative_decimal_or_none(
        value=threshold_absolute,
        field_name="threshold_absolute",
    )

    if (
        normalized_percent is None
        and normalized_absolute is None
    ):
        raise AlertRuleSettingsValidationError(
            "At least one threshold must be provided."
        )

    if (
        normalized_percent is not None
        and normalized_absolute is not None
    ):
        raise AlertRuleSettingsValidationError(
            "Only one threshold type can be configured at a time."
        )

    return _update_target_alert_rule(
        user=user,
        target_id=target_id,
        alert_type=alert_type,
        updates={
            "threshold_percent": normalized_percent,
            "threshold_absolute": normalized_absolute,
        },
    )


def set_target_alert_rule_cooldown(
    *,
    user,
    target_id: UUID | str,
    alert_type: str,
    cooldown_minutes: int,
) -> TargetAlertRuleUpdateResult:
    """Set the silence period for one target-specific alert rule."""

    try:
        normalized_cooldown = int(cooldown_minutes)
    except (TypeError, ValueError) as exc:
        raise AlertRuleSettingsValidationError(
            "cooldown_minutes must be an integer."
        ) from exc

    if normalized_cooldown < 0:
        raise AlertRuleSettingsValidationError(
            "cooldown_minutes cannot be negative."
        )

    if normalized_cooldown > MAX_ALERT_RULE_COOLDOWN_MINUTES:
        raise AlertRuleSettingsValidationError(
            "cooldown_minutes cannot be greater than "
            f"{MAX_ALERT_RULE_COOLDOWN_MINUTES}."
        )

    return _update_target_alert_rule(
        user=user,
        target_id=target_id,
        alert_type=alert_type,
        updates={
            "cooldown_minutes": normalized_cooldown,
        },
    )


def _update_target_alert_rule(
    *,
    user,
    target_id: UUID | str,
    alert_type: str,
    updates: dict[str, Any],
) -> TargetAlertRuleUpdateResult:
    _validate_alert_type(alert_type=alert_type)

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

        current_rule = get_effective_alert_rule(
            target=target,
            alert_type=alert_type,
        )

        values = {
            "threshold_percent": current_rule.threshold_percent,
            "threshold_absolute": current_rule.threshold_absolute,
            "cooldown_minutes": current_rule.cooldown_minutes,
            "is_enabled": current_rule.is_enabled,
        }
        values.update(updates)

        if all(
            getattr(current_rule, field_name) == value
            for field_name, value in updates.items()
        ):
            return TargetAlertRuleUpdateResult(
                target=target,
                rule=current_rule,
                changed=False,
            )

        AlertRule.objects.update_or_create(
            target=target,
            alert_type=alert_type,
            defaults={
                "user": user,
                **values,
            },
        )

        updated_rule = get_effective_alert_rule(
            target=target,
            alert_type=alert_type,
        )

    return TargetAlertRuleUpdateResult(
        target=target,
        rule=updated_rule,
        changed=True,
    )


def _validate_alert_type(*, alert_type: str) -> None:
    if alert_type not in SUPPORTED_TARGET_ALERT_TYPES:
        raise AlertRuleSettingsValidationError(
            f"Unsupported alert rule type: {alert_type}."
        )


def _to_non_negative_decimal_or_none(
    *,
    value: Decimal | int | float | str | None,
    field_name: str,
) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AlertRuleSettingsValidationError(
            f"{field_name} must be a decimal number or null."
        ) from exc

    if decimal_value < 0:
        raise AlertRuleSettingsValidationError(
            f"{field_name} cannot be negative."
        )

    return decimal_value
