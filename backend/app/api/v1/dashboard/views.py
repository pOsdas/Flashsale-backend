from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.v1.dashboard.serializers import DashboardSerializer
from app.api.v1.dashboard.services import DashboardService


@extend_schema(
    tags=["Dashboard",],
    summary="Get user dashboard",
    description=(
        "Returns aggregated account statistics for the current user. "
        "This endpoint does not change any data."
    ),
    responses={
        200: OpenApiResponse(
            response=DashboardSerializer,
            description="Dashboard data was successfully returned.",
        ),
    },
)
class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated,]

    def get(self, request):
        dashboard = DashboardService().get_dashboard(
            user=request.user,
        )

        serializer = DashboardSerializer(
            dashboard,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
