from django.urls import path

from app.api.v1.fetcher.views import import_fetcher_items


urlpatterns = [
    path("import", import_fetcher_items, name="fetcher-import"),
]
