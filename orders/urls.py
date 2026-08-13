from __future__ import annotations

from django.urls import URLPattern, path

from .views import CheckoutView, OrderConfirmationView

app_name = "orders"

urlpatterns: list[URLPattern] = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path(
        "orders/<str:order_number>/confirmation/",
        OrderConfirmationView.as_view(),
        name="confirmation",
    ),
]
