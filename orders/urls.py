from __future__ import annotations

from django.urls import URLPattern, path

from .views import CheckoutView, OrderConfirmationView, OrderTrackingView

app_name = "orders"

urlpatterns: list[URLPattern] = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path(
        "orders/<str:order_number>/confirmation/",
        OrderConfirmationView.as_view(),
        name="confirmation",
    ),
    # Must stay exactly "track/" — notifications.whatsapp.message_builder.
    # TRACKING_URL_PATH ("/track/") is a contract already committed to in
    # every status-update message sent since Stage 9.
    path("track/", OrderTrackingView.as_view(), name="tracking"),
]
