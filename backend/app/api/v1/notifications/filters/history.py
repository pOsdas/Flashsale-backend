from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError


class NotificationDeliveryHistoryFilter:
    def __init__(self, *, queryset, query_params):
        self.queryset = queryset
        self.query_params = query_params

    def apply(self):
        queryset = self.queryset

        queryset = self._filter_by_status(queryset)
        queryset = self._filter_by_channel_id(queryset)
        # queryset = self._filter_by_alert_type(queryset)
        queryset = self._filter_by_created_from(queryset)
        queryset = self._filter_by_created_to(queryset)

        return queryset

    def _filter_by_status(self, queryset):
        status = self.query_params.get("status")

        if not status:
            return queryset

        return queryset.filter(status=status)

    def _filter_by_channel_id(self, queryset):
        channel_id = self.query_params.get("channel_id")

        if not channel_id:
            return queryset

        if not channel_id.isdigit():
            raise ValidationError(
                {
                    "channel_id": "channel_id должен быть числом."
                }
            )

        return queryset.filter(channel_id=int(channel_id))

    # def _filter_by_alert_type(self, queryset):
    #     alert_type = self.query_params.get("alert_type")
    #
    #     if not alert_type:
    #         return queryset
    #
    #     return queryset.filter(alert__type=alert_type)

    def _filter_by_created_from(self, queryset):
        created_from = self.query_params.get("created_from")

        if not created_from:
            return queryset

        parsed_date = parse_date(created_from)

        if parsed_date is None:
            raise ValidationError(
                {
                    "created_from": "Дата должна быть в формате YYYY-MM-DD."
                }
            )

        return queryset.filter(created_at__date__gte=parsed_date)

    def _filter_by_created_to(self, queryset):
        created_to = self.query_params.get("created_to")

        if not created_to:
            return queryset

        parsed_date = parse_date(created_to)

        if parsed_date is None:
            raise ValidationError(
                {
                    "created_to": "Дата должна быть в формате YYYY-MM-DD."
                }
            )

        return queryset.filter(created_at__date__lte=parsed_date)
