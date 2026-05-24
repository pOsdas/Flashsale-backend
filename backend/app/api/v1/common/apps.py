from django.apps import AppConfig


class V1CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app.api.v1.common"
    verbose_name = "Common"
