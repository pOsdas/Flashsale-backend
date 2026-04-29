from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from strawberry.django.views import GraphQLView

from app.api.v1.schema import schema

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql/", GraphQLView.as_view(schema=schema)),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
