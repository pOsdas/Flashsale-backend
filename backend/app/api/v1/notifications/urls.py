from django.urls import path

from app.api.v1.notifications.views import (
    NotificationChannelDetailView,
    NotificationChannelListCreateView,
    TelegramConnectLinkView,
    TelegramOnboardingView,
    NotificationDeliveryHistoryDetailView,
    NotificationDeliveryHistoryListView,
)


urlpatterns = [
    path(
        "channels/",
        NotificationChannelListCreateView.as_view(),
        name="notification-channel-list-create",
    ),
    path(
        "channels/<int:pk>/",
        NotificationChannelDetailView.as_view(),
        name="notification-channel-detail",
    ),
    path(
        "telegram/connect-link/",
        TelegramConnectLinkView.as_view(),
        name="telegram-connect-link",
    ),
    path(
        "telegram/onboarding/",
        TelegramOnboardingView.as_view(),
        name="telegram-onboarding",
    ),
    path(
        "history/",
        NotificationDeliveryHistoryListView.as_view(),
        name="notification-history-list",
    ),
    path(
        "history/<int:pk>/",
        NotificationDeliveryHistoryDetailView.as_view(),
        name="notification-history-detail",
    ),
]
