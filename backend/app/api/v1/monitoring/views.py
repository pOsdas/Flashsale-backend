from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from app.api.v1.monitoring.models import (
    Alert,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    MonitoringTargetStatus,
    ProductSnapshot,
)
from app.api.v1.monitoring.serializers import (
    AlertQuerySerializer,
    AlertSerializer,
    MonitoringTargetSerializer,
    ProductSnapshotSerializer,
)
from app.api.v1.monitoring.services.target_service import create_monitoring_target


@extend_schema_view(
    get=extend_schema(
        tags=["Monitoring"],
        parameters=[
            OpenApiParameter(
                name="marketplace",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[choice[0] for choice in Marketplace.choices],
                description="Filter targets by marketplace.",
            ),
            OpenApiParameter(
                name="role",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[choice[0] for choice in MonitoringTargetRole.choices],
                description="Filter targets by role.",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[choice[0] for choice in MonitoringTargetStatus.choices],
                description="Filter targets by status.",
            ),
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter active or inactive monitoring targets.",
            ),
        ],
    ),
    post=extend_schema(
        tags=["Monitoring"],
    ),
)
class MonitoringTargetListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = MonitoringTargetSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = (
            MonitoringTarget.objects
            .filter(user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "snapshots",
                    queryset=ProductSnapshot.objects.order_by("-checked_at"),
                )
            )
            .order_by("-created_at")
        )

        marketplace = self.request.query_params.get("marketplace")
        role = self.request.query_params.get("role")
        status = self.request.query_params.get("status")
        is_active = self.request.query_params.get("is_active")

        if marketplace:
            queryset = queryset.filter(marketplace=marketplace)

        if role:
            queryset = queryset.filter(role=role)

        if status:
            queryset = queryset.filter(status=status)

        if is_active in ("true", "True", "1"):
            queryset = queryset.filter(is_active=True)

        if is_active in ("false", "False", "0"):
            queryset = queryset.filter(is_active=False)

        return queryset

    def perform_create(self, serializer):
        target = create_monitoring_target(
            user=self.request.user,
            validated_data=serializer.validated_data,
        )

        serializer.instance = target


@extend_schema(tags=["Monitoring"])
class ProductSnapshotListAPIView(generics.ListAPIView):
    serializer_class = ProductSnapshotSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        target = get_object_or_404(
            MonitoringTarget.objects.filter(user=self.request.user),
            id=self.kwargs["target_id"],
        )

        return (
            ProductSnapshot.objects
            .filter(target=target)
            .order_by("-checked_at")
        )


@extend_schema(
    tags=["Monitoring"],
    parameters=[
        OpenApiParameter(
            name="target_id",
            description="Filter alerts by monitoring target UUID",
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="alert_type",
            description="Filter alerts by alert type",
            required=False,
            type=str,
            enum=[
                "price_changed",
                "price_dropped",
                "price_increased",
                "availability_changed",
                "became_available",
                "became_unavailable",
                "rating_changed",
                "reviews_count_changed",
                "title_changed",
            ],
        ),
        OpenApiParameter(
            name="severity",
            description="Filter alerts by severity",
            required=False,
            type=str,
            enum=[
                "low",
                "medium",
                "high",
                "critical",
            ],
        ),
        OpenApiParameter(
            name="status",
            description="Filter alerts by status",
            required=False,
            type=str,
            enum=[
                "new",
                "sent",
                "skipped",
                "failed",
            ],
        ),
    ],
)
class AlertListAPIView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = (
            Alert.objects
            .filter(user=self.request.user)
            .select_related(
                "target",
                "snapshot",
            )
            .order_by("-created_at")
        )

        target_id = self.request.query_params.get("target_id")
        alert_type = self.request.query_params.get("alert_type")
        severity = self.request.query_params.get("severity")
        status = self.request.query_params.get("status")

        if target_id:
            queryset = queryset.filter(target_id=target_id)

        if alert_type:
            queryset = queryset.filter(alert_type=alert_type)

        if severity:
            queryset = queryset.filter(severity=severity)

        if status:
            queryset = queryset.filter(status=status)

        return queryset
