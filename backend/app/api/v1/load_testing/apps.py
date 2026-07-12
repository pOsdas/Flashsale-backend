from django.apps import AppConfig
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_load_testing_configuration(app_configs, **kwargs):
    from django.conf import settings

    if not getattr(settings, "LOAD_TESTING_ENABLED", False):
        return []

    api_key = str(
        getattr(settings, "LOAD_TESTING_API_KEY", "") or ""
    ).strip()

    if len(api_key) < 24:
        return [
            Error(
                "LOAD_TESTING_ENABLED requires a non-empty "
                "LOAD_TESTING_API_KEY with at least 24 characters.",
                id="load_testing.E001",
            )
        ]

    if str(getattr(settings, "APP_ENV", "")).lower() in {
        "prod",
        "production",
    }:
        return [
            Error(
                "LOAD_TESTING_ENABLED must never be enabled in production.",
                id="load_testing.E002",
            )
        ]

    return []


class V1LoadTestingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app.api.v1.load_testing"
    label = "load_testing"
    verbose_name = "Load testing support"
