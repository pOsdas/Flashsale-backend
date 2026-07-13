from types import SimpleNamespace

from django.test import SimpleTestCase

from app.api.v1.monitoring.models import MonitoringTargetStatus
from app.api.v1.monitoring.services.monitoring_state import (
    MONITORING_STATE_ACTIVE,
    MONITORING_STATE_INACTIVE,
    MONITORING_STATE_PAUSED,
    MONITORING_STATE_STOPPED_BY_ERROR,
    get_monitoring_state,
    get_monitoring_state_title,
)


class MonitoringStateTests(SimpleTestCase):
    def test_active_target(self) -> None:
        target = SimpleNamespace(
            status=MonitoringTargetStatus.ACTIVE,
            is_active=True,
        )

        self.assertEqual(
            get_monitoring_state(target),
            MONITORING_STATE_ACTIVE,
        )
        self.assertEqual(
            get_monitoring_state_title(target),
            "Отслеживание активно",
        )

    def test_paused_target(self) -> None:
        target = SimpleNamespace(
            status=MonitoringTargetStatus.PAUSED,
            is_active=False,
        )

        self.assertEqual(
            get_monitoring_state(target),
            MONITORING_STATE_PAUSED,
        )

    def test_failed_target(self) -> None:
        target = SimpleNamespace(
            status=MonitoringTargetStatus.FAILED,
            is_active=True,
        )

        self.assertEqual(
            get_monitoring_state(target),
            MONITORING_STATE_STOPPED_BY_ERROR,
        )
        self.assertEqual(
            get_monitoring_state_title(target),
            "Проверки остановлены из-за ошибки",
        )

    def test_inconsistent_inactive_target(self) -> None:
        target = SimpleNamespace(
            status=MonitoringTargetStatus.ACTIVE,
            is_active=False,
        )

        self.assertEqual(
            get_monitoring_state(target),
            MONITORING_STATE_INACTIVE,
        )