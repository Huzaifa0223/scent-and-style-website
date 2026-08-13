from __future__ import annotations

from django.urls import URLPattern, path

from cart.views import (
    CartAddView,
    CartClearView,
    CartDecrementView,
    CartIncrementView,
    CartRemoveView,
)

app_name = "cart"

urlpatterns: list[URLPattern] = [
    path("add/", CartAddView.as_view(), name="add"),
    path("items/<int:item_id>/increment/", CartIncrementView.as_view(), name="increment"),
    path("items/<int:item_id>/decrement/", CartDecrementView.as_view(), name="decrement"),
    path("items/<int:item_id>/remove/", CartRemoveView.as_view(), name="remove"),
    path("clear/", CartClearView.as_view(), name="clear"),
]
