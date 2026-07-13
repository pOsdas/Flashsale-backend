from app.api.v1.monitoring.models import (
    MonitoringTarget,
    MonitoringTargetStatus,
)


MONITORING_STATE_ACTIVE = "active"
MONITORING_STATE_PAUSED = "paused"
MONITORING_STATE_STOPPED_BY_ERROR = "stopped_by_error"
MONITORING_STATE_INACTIVE = "inactive"


MONITORING_STATE_TITLES = {
    MONITORING_STATE_ACTIVE: "Отслеживание активно",
    MONITORING_STATE_PAUSED: "Отслеживание приостановлено",
    MONITORING_STATE_STOPPED_BY_ERROR: (
        "Проверки остановлены из-за ошибки"
    ),
    MONITORING_STATE_INACTIVE: "Отслеживание отключено",
}


def get_monitoring_state(
    target: MonitoringTarget,
) -> str:
    """
    Return one unambiguous client-facing monitoring state.

    Internal status and is_active fields remain unchanged.
    """

    if (
        target.status == MonitoringTargetStatus.ACTIVE
        and target.is_active
    ):
        return MONITORING_STATE_ACTIVE

    if target.status == MonitoringTargetStatus.FAILED:
        return MONITORING_STATE_STOPPED_BY_ERROR

    if target.status == MonitoringTargetStatus.PAUSED:
        return MONITORING_STATE_PAUSED

    if not target.is_active:
        return MONITORING_STATE_INACTIVE

    return MONITORING_STATE_INACTIVE


def get_monitoring_state_title(
    target: MonitoringTarget,
) -> str:
    monitoring_state = get_monitoring_state(target)

    return MONITORING_STATE_TITLES[monitoring_state]