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
    path(f"{API_PREFIX}{API_V1_PREFIX}/fetcher/", include("app.api.v1.fetcher.urls")),
]

if settings.DEBUG:
    from drf_spectacular.views import (
        SpectacularAPIView,
        SpectacularSwaggerView,
        SpectacularRedocView,
    )
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    urlpatterns += [
        # Маршруты для OpenAPI схемы и Swagger UI / Redoc
        path(f'{API_PREFIX}{API_V1_PREFIX}/schema/', SpectacularAPIView.as_view(), name='schema'),
        path(f'{API_PREFIX}{API_V1_PREFIX}/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
        path(f'{API_PREFIX}{API_V1_PREFIX}/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui')
    ]
