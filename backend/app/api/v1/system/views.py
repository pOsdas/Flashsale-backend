from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.api.v1.system.checks import SystemHealthChecker
from app.api.v1.system.parser_health import ParserHealthChecker
from app.api.v1.system.serializers import SystemHealthSerializer, ParserHealthSerializer


@extend_schema(
    tags=["System"],
    summary="Get system health status",
    description=(
        "Checks core system dependencies: database, Redis, RabbitMQ, "
        "go_fetcher and Telegram configuration. "
        "This endpoint is intended for internal admin diagnostics."
    ),
    responses={
        200: OpenApiResponse(
            response=SystemHealthSerializer,
            description="System is healthy or degraded.",
        ),
        503: OpenApiResponse(
            response=SystemHealthSerializer,
            description="System has at least one unhealthy critical dependency.",
        ),
    },
)
class SystemHealthView(APIView):
    permission_classes = [permissions.IsAdminUser,]

    def get(self, request):
        health = SystemHealthChecker().run()

        response_status = status.HTTP_200_OK

        if health["status"] == "unhealthy":
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(
            health,
            status=response_status,
        )


@extend_schema(
    tags=["System"],
    summary="Get parser health status",
    description=(
        "Runs manual parser diagnostics through go_fetcher. "
        "This endpoint checks whether marketplace parsers are currently able "
        "to extract product data. It does not create MonitoringTarget, "
        "ProductSnapshot or Alert records."
    ),
    responses={
        200: OpenApiResponse(
            response=ParserHealthSerializer,
            description="Parsers are healthy or degraded.",
        ),
        503: OpenApiResponse(
            response=ParserHealthSerializer,
            description="At least one critical parser check failed.",
        ),
    },
)
class ParserHealthView(APIView):
    permission_classes = [permissions.IsAdminUser,]

    def get(self, request):
        parser_health = ParserHealthChecker().run()

        response_status = status.HTTP_200_OK

        if parser_health["status"] == "unhealthy":
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(
            parser_health,
            status=response_status,
        )
