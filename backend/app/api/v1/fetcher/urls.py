from django.urls import path

from app.api.v1.fetcher.views import import_fetcher_items, fetch_product


urlpatterns = [
    path("import/", import_fetcher_items, name="fetcher-import"),
    path("fetch-product/", fetch_product, name="fetch-product"),
]
