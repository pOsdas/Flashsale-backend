from django.apps import AppConfig


class V1MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app.api.v1.monitoring"
    verbose_name = "Monitoring"
