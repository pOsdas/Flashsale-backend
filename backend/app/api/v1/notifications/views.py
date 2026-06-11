from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from app.api.v1.notifications.filters.history import NotificationDeliveryHistoryFilter
from app.api.v1.notifications.models import NotificationDelivery
from app.api.v1.notifications.serializers import NotificationDeliveryHistorySerializer

from app.api.v1.notifications.models import NotificationChannel
from app.api.v1.notifications.serializers import (
    NotificationChannelSerializer,
    TelegramConnectLinkSerializer,
    TelegramOnboardingResponseSerializer,
    TelegramOnboardingSerializer,
)
from app.api.v1.notifications.services.telegram_onboarding import (
    TelegramOnboardingService,
)


@extend_schema(tags=["Notifications"])
class NotificationChannelListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationChannelSerializer

    def get_queryset(self):
        return (
            NotificationChannel.objects
            .filter(user=self.request.user)
            .order_by("-created_at")
        )


@extend_schema(tags=["Notifications"])
class NotificationChannelDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationChannelSerializer
    http_method_names = [
        "get",
        "patch",
        "delete",
        "head",
        "options",
    ]

    def get_queryset(self):
        return NotificationChannel.objects.filter(
            user=self.request.user,
        )


@extend_schema(tags=["Notifications"])
class TelegramConnectLinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        connect_link = TelegramOnboardingService.build_connect_link(
            user=request.user,
        )

        serializer = TelegramConnectLinkSerializer(
            {
                "token": connect_link.token,
                "url": connect_link.url,
                "expires_in_seconds": connect_link.expires_in_seconds,
            }
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Debug (Notifications)"],
    request=TelegramOnboardingSerializer,
    responses={
        200: TelegramOnboardingResponseSerializer,
        201: TelegramOnboardingResponseSerializer,
    },
)
class TelegramOnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TelegramOnboardingSerializer(
            data=request.data,
            context={
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)

        channel = serializer.save()

        response_serializer = TelegramOnboardingResponseSerializer(channel)

        response_status = (
            status.HTTP_201_CREATED
            if getattr(serializer, "created", False)
            else status.HTTP_200_OK
        )

        return Response(
            response_serializer.data,
            status=response_status,
        )


@extend_schema(tags=["Notification History"])
class NotificationDeliveryHistoryListView(generics.ListAPIView):
    serializer_class = NotificationDeliveryHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = (
            NotificationDelivery.objects
            .select_related(
                "channel",
                "alert",
            )
            .filter(user=self.request.user)
            .order_by("-created_at")
        )

        return NotificationDeliveryHistoryFilter(
            queryset=queryset,
            query_params=self.request.query_params,
        ).apply()


@extend_schema(tags=["Notification History"])
class NotificationDeliveryHistoryDetailView(generics.RetrieveAPIView):
    serializer_class = NotificationDeliveryHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            NotificationDelivery.objects
            .select_related(
                "channel",
                "alert",
            )
            .filter(user=self.request.user)
        )
