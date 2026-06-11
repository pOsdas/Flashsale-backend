from django.urls import path

from app.api.v1.dashboard.views import DashboardView


app_name = "dashboard"


urlpatterns = [
    path(
        "",
        DashboardView.as_view(),
        name="dashboard",
    ),
]
