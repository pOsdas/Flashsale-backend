from django.apps import AppConfig


class V1FetcherConfig(AppConfig):
    big_auto_field = "django.db.models.BigAutoField"
    name = "app.api.v1.fetcher"
    verbose_name = "Fetcher"
