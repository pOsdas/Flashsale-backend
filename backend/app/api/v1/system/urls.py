from django.urls import path

from app.api.v1.system.views import SystemHealthView, ParserHealthView


app_name = "system"


urlpatterns = [
    path("health/", SystemHealthView.as_view(), name="system-health"),
    path("parser-health/", ParserHealthView.as_view(), name="parser-health"),
]
