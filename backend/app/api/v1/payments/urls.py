from django.urls import path

from app.api.v1.payments.views import payment_webhook_view

urlpatterns = [
    path("webhook/", payment_webhook_view, name="payment-webhook"),
]