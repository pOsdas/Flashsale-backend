from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.v1.monitoring.models import (
    Alert,
    Marketplace,
    MonitoringTarget,
    MonitoringTargetRole,
    MonitoringTargetStatus,
    ProductSnapshot,
)
from app.api.v1.monitoring.serializers import (
    AlertSerializer,
    MonitoringTargetActionErrorSerializer,
    MonitoringTargetCheckNowResponseSerializer,
    MonitoringTargetSerializer,
    MonitoringTargetUpdateSerializer,
    ProductPreviewErrorResponseSerializer,
    ProductPreviewRequestSerializer,
    ProductPreviewResponseSerializer,
    ProductSnapshotSerializer,
)
from app.api.v1.monitoring.services.product_preview import (
    ProductPreviewError,
    ProductPreviewService,
)
from app.api.v1.monitoring.services.target_service import (
    MonitoringTargetCheckBusyError,
    MonitoringTargetCheckError,
    MonitoringTargetNotFoundError,
    MonitoringTargetUpdateError,
    check_monitoring_target_now,
    create_monitoring_target,
    delete_monitoring_target,
    get_monitoring_target_for_user,
    update_monitoring_target,
)


@extend_schema_view(
    get=extend_schema(
        tags=["Monitoring"],
        parameters=[
            OpenApiParameter(
                name="marketplace",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[
                    choice[0]
                    for choice in Marketplace.choices
                ],
                description="Filter targets by marketplace.",
            ),
            OpenApiParameter(
                name="role",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[
                    choice[0]
                    for choice in MonitoringTargetRole.choices
                ],
                description="Filter targets by role.",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=[
                    choice[0]
                    for choice in MonitoringTargetStatus.choices
                ],
                description="Filter targets by status.",
            ),
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Filter active or inactive monitoring targets."
                ),
            ),
        ],
    ),
    post=extend_schema(
        tags=["Monitoring"],
    ),
)
class MonitoringTargetListCreateAPIView(
    generics.ListCreateAPIView,
):
    serializer_class = MonitoringTargetSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = (
            MonitoringTarget.objects
            .filter(user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "snapshots",
                    queryset=(
                        ProductSnapshot.objects
                        .order_by("-checked_at")
                    ),
                )
            )
            .order_by("-created_at")
        )

        marketplace = self.request.query_params.get(
            "marketplace"
        )
        role = self.request.query_params.get("role")
        target_status = self.request.query_params.get(
            "status"
        )
        is_active = self.request.query_params.get(
            "is_active"
        )

        if marketplace:
            queryset = queryset.filter(
                marketplace=marketplace,
            )

        if role:
            queryset = queryset.filter(
                role=role,
            )

        if target_status:
            queryset = queryset.filter(
                status=target_status,
            )

        if is_active in ("true", "True", "1"):
            queryset = queryset.filter(
                is_active=True,
            )

        if is_active in ("false", "False", "0"):
            queryset = queryset.filter(
                is_active=False,
            )

        return queryset

    def perform_create(self, serializer):
        target = create_monitoring_target(
            user=self.request.user,
            validated_data=serializer.validated_data,
        )

        serializer.instance = target


class MonitoringTargetDetailAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Monitoring"],
        responses={
            200: MonitoringTargetSerializer,
            404: OpenApiResponse(
                response=MonitoringTargetActionErrorSerializer,
                description=(
                    "The target does not exist or belongs "
                    "to another user."
                ),
            ),
        },
    )
    def get(
        self,
        request,
        target_id,
    ):
        try:
            target = get_monitoring_target_for_user(
                user=request.user,
                target_id=target_id,
            )

        except MonitoringTargetNotFoundError as exc:
            return self._not_found_response(exc=exc)

        serializer = MonitoringTargetSerializer(
            instance=target,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Monitoring"],
        request=MonitoringTargetUpdateSerializer,
        responses={
            200: MonitoringTargetSerializer,
            400: OpenApiResponse(
                response=MonitoringTargetActionErrorSerializer,
                description="The update data is invalid.",
            ),
            404: OpenApiResponse(
                response=MonitoringTargetActionErrorSerializer,
                description=(
                    "The target does not exist or belongs "
                    "to another user."
                ),
            ),
        },
    )
    def patch(
        self,
        request,
        target_id,
    ):
        request_serializer = MonitoringTargetUpdateSerializer(
            data=request.data,
        )
        request_serializer.is_valid(
            raise_exception=True,
        )

        try:
            target = update_monitoring_target(
                user=request.user,
                target_id=target_id,
                validated_data=(
                    request_serializer.validated_data
                ),
            )

        except MonitoringTargetNotFoundError as exc:
            return self._not_found_response(exc=exc)

        except MonitoringTargetUpdateError as exc:
            return Response(
                {
                    "success": False,
                    "error_code": "invalid_target_update",
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_serializer = MonitoringTargetSerializer(
            instance=target,
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Monitoring"],
        request=None,
        responses={
            204: OpenApiResponse(
                description=(
                    "The monitoring target was permanently deleted."
                ),
            ),
            404: OpenApiResponse(
                response=MonitoringTargetActionErrorSerializer,
                description=(
                    "The target does not exist or belongs "
                    "to another user."
                ),
            ),
        },
    )
    def delete(
        self,
        request,
        target_id,
    ):
        try:
            delete_monitoring_target(
                user=request.user,
                target_id=target_id,
            )

        except MonitoringTargetNotFoundError as exc:
            return self._not_found_response(exc=exc)

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )

    @staticmethod
    def _not_found_response(
        *,
        exc: Exception,
    ) -> Response:
        return Response(
            {
                "success": False,
                "error_code": "target_not_found",
                "error": str(exc),
            },
            status=status.HTTP_404_NOT_FOUND,
        )


@extend_schema(
    tags=["Monitoring"],
    description=(
        "Immediately checks an existing monitoring target. "
        "The operation does not create another MonitoringTarget. "
        "It forces a refresh through the shared product cache, "
        "creates a ProductSnapshot and detects product changes."
    ),
    request=None,
    responses={
        200: OpenApiResponse(
            response=MonitoringTargetCheckNowResponseSerializer,
            description=(
                "The target was successfully checked."
            ),
        ),
        404: OpenApiResponse(
            response=MonitoringTargetActionErrorSerializer,
            description=(
                "The target does not exist or belongs "
                "to another user."
            ),
        ),
        409: OpenApiResponse(
            response=MonitoringTargetActionErrorSerializer,
            description=(
                "Another process is currently refreshing "
                "the same product."
            ),
        ),
        502: OpenApiResponse(
            response=MonitoringTargetActionErrorSerializer,
            description=(
                "The marketplace product check failed."
            ),
        ),
    },
)
class MonitoringTargetCheckNowAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(
        self,
        request,
        target_id,
    ):
        try:
            result = check_monitoring_target_now(
                user=request.user,
                target_id=target_id,
            )

        except MonitoringTargetNotFoundError as exc:
            return Response(
                {
                    "success": False,
                    "error_code": "target_not_found",
                    "error": str(exc),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except MonitoringTargetCheckBusyError as exc:
            return Response(
                {
                    "success": False,
                    "error_code": "refresh_busy",
                    "error": str(exc),
                },
                status=status.HTTP_409_CONFLICT,
            )

        except MonitoringTargetCheckError as exc:
            return Response(
                {
                    "success": False,
                    "error_code": "check_failed",
                    "error": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        response_serializer = (
            MonitoringTargetCheckNowResponseSerializer(
                instance={
                    "success": True,
                    "target": result.target,
                    "snapshot": result.snapshot,
                    "alerts_count": result.alerts_count,
                    "cache_source": result.cache_source,
                    "cache_is_stale": (
                        result.cache_is_stale
                    ),
                    "effective_cache_minutes": (
                        result.effective_cache_minutes
                    ),
                }
            )
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Monitoring"])
class ProductSnapshotListAPIView(
    generics.ListAPIView,
):
    serializer_class = ProductSnapshotSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        target = get_object_or_404(
            MonitoringTarget.objects.filter(
                user=self.request.user,
            ),
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
            description=(
                "Filter alerts by monitoring target UUID."
            ),
            required=False,
            type=OpenApiTypes.UUID,
        ),
        OpenApiParameter(
            name="alert_type",
            description="Filter alerts by alert type.",
            required=False,
            type=OpenApiTypes.STR,
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
            description="Filter alerts by severity.",
            required=False,
            type=OpenApiTypes.STR,
            enum=[
                "low",
                "medium",
                "high",
                "critical",
            ],
        ),
        OpenApiParameter(
            name="status",
            description="Filter alerts by status.",
            required=False,
            type=OpenApiTypes.STR,
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

        target_id = self.request.query_params.get(
            "target_id"
        )
        alert_type = self.request.query_params.get(
            "alert_type"
        )
        severity = self.request.query_params.get(
            "severity"
        )
        alert_status = self.request.query_params.get(
            "status"
        )

        if target_id:
            queryset = queryset.filter(
                target_id=target_id,
            )

        if alert_type:
            queryset = queryset.filter(
                alert_type=alert_type,
            )

        if severity:
            queryset = queryset.filter(
                severity=severity,
            )

        if alert_status:
            queryset = queryset.filter(
                status=alert_status,
            )

        return queryset


@extend_schema(
    tags=["Product Preview"],
    description=(
        "Checks whether a product can be parsed from the "
        "provided marketplace URL. This endpoint does not "
        "create MonitoringTarget, ProductSnapshot or Alert "
        "records."
    ),
    request=ProductPreviewRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=ProductPreviewResponseSerializer,
            description=(
                "Product was successfully parsed."
            ),
        ),
        400: OpenApiResponse(
            response=ProductPreviewErrorResponseSerializer,
            description=(
                "Product could not be parsed or request "
                "data is invalid."
            ),
        ),
    },
)
class ProductPreviewView(APIView):
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def post(self, request):
        serializer = ProductPreviewRequestSerializer(
            data=request.data,
        )
        serializer.is_valid(
            raise_exception=True,
        )

        service = ProductPreviewService()

        try:
            preview = service.preview_product(
                marketplace=(
                    serializer.validated_data["marketplace"]
                ),
                url=serializer.validated_data["url"],
            )

        except ProductPreviewError as exc:
            return Response(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "product": {
                    "external_id": preview.external_id,
                    "title": preview.title,
                    "seller_name": preview.seller_name,
                    "brand": preview.brand,
                    "price": preview.price,
                    "old_price": preview.old_price,
                    "currency": preview.currency,
                    "is_available": preview.is_available,
                    "rating": preview.rating,
                    "reviews_count": (
                        preview.reviews_count
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )
