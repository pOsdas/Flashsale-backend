from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from app.api.v1.monitoring.models import (
    AlertRule,
    MonitoringTarget,
)
from app.api.v1.monitoring.services.alert_rule_constants import (
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

    if alert_type not in SUPPORTED_TARGET_ALERT_TYPES:
        raise AlertRuleSettingsValidationError(
            f"Unsupported alert rule type: {alert_type}."
        )

    if not isinstance(is_enabled, bool):
        raise AlertRuleSettingsValidationError(
            "is_enabled must be a boolean."
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

        current_rule = get_effective_alert_rule(
            target=target,
            alert_type=alert_type,
        )

        if current_rule.is_enabled == is_enabled:
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
                "threshold_percent": current_rule.threshold_percent,
                "threshold_absolute": current_rule.threshold_absolute,
                "cooldown_minutes": current_rule.cooldown_minutes,
                "is_enabled": is_enabled,
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
