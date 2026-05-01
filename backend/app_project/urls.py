from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from strawberry.django.views import GraphQLView

from app.core.config import get_settings
from app.api.v1.schema import schema

core_settings = get_settings()

API_PREFIX = core_settings.api.prefix
API_V1_PREFIX = core_settings.api.v1.prefix

urlpatterns = [
    path(f"{API_PREFIX}{API_V1_PREFIX}/admin/", admin.site.urls),
    path(f"{API_PREFIX}{API_V1_PREFIX}/graphql/", GraphQLView.as_view(schema=schema)),
    path(f"{API_PREFIX}{API_V1_PREFIX}/payments/", include("app.api.v1.payments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
