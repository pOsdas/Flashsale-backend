from django.urls import path

from app.api.v1.monitoring.views import (
    AlertListAPIView,
    MonitoringTargetAlertSettingsAPIView,
    MonitoringTargetCheckNowAPIView,
    MonitoringTargetDetailAPIView,
    MonitoringTargetListCreateAPIView,
    MonitoringTargetPauseAPIView,
    MonitoringTargetResumeAPIView,
    ProductPreviewView,
    ProductSnapshotListAPIView,
)


app_name = "monitoring"


urlpatterns = [
    path(
        "targets/",
        MonitoringTargetListCreateAPIView.as_view(),
        name="target-list-create",
    ),
    path(
        "targets/<uuid:target_id>/",
        MonitoringTargetDetailAPIView.as_view(),
        name="target-detail",
    ),
    path(
        "targets/<uuid:target_id>/alert-settings/",
        MonitoringTargetAlertSettingsAPIView.as_view(),
        name="target-alert-settings",
    ),
    path(
        "targets/<uuid:target_id>/pause/",
        MonitoringTargetPauseAPIView.as_view(),
        name="target-pause",
    ),
    path(
        "targets/<uuid:target_id>/resume/",
        MonitoringTargetResumeAPIView.as_view(),
        name="target-resume",
    ),
    path(
        "targets/<uuid:target_id>/check-now/",
        MonitoringTargetCheckNowAPIView.as_view(),
        name="target-check-now",
    ),
    path(
        "targets/<uuid:target_id>/snapshots/",
        ProductSnapshotListAPIView.as_view(),
        name="target-snapshot-list",
    ),
    path(
        "alerts/",
        AlertListAPIView.as_view(),
        name="alert-list",
    ),
    path(
        "products/preview/",
        ProductPreviewView.as_view(),
        name="product-preview",
    ),
]
