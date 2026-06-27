from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from app.api.v1.monitoring.services.target_duplicate_service import (
    find_existing_monitoring_target,
)


class MonitoringTargetDuplicateServiceTests(SimpleTestCase):
    @patch(
        "app.api.v1.monitoring.services.target_duplicate_service."
        "MonitoringTarget.objects"
    )
    def test_queries_by_user_marketplace_and_identity(
        self,
        objects_mock,
    ) -> None:
        queryset = Mock()
        objects_mock.filter.return_value = queryset
        queryset.filter.return_value = queryset
        queryset.order_by.return_value = queryset
        expected = object()
        queryset.first.return_value = expected

        result = find_existing_monitoring_target(
            user=object(),
            marketplace="wb",
            external_id="123",
            url="https://example.com/product",
        )

        self.assertIs(result, expected)
        self.assertEqual(objects_mock.filter.call_count, 1)
        queryset.first.assert_called_once_with()
