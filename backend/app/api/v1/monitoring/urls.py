from django.urls import path

from app.api.v1.monitoring.views import (
    AlertListAPIView,
    MonitoringTargetCheckNowAPIView,
    MonitoringTargetDetailAPIView,
    MonitoringTargetListCreateAPIView,
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
