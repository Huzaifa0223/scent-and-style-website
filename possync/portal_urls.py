"""Mounted at ``admin-portal/pos/`` by ``config/urls.py``."""

from __future__ import annotations

from django.urls import URLPattern, path

from . import portal_views as views

app_name = "possync"

urlpatterns: list[URLPattern] = [
    path("", views.PosMappingView.as_view(), name="mapping"),
    path("upload/", views.PosCsvUploadView.as_view(), name="upload"),
    path("export/", views.PosMappingExportView.as_view(), name="export"),
    path("price-mismatches/", views.PosPriceMismatchView.as_view(), name="price_mismatches"),
    path("orders-since/", views.PosOrdersSinceView.as_view(), name="orders_since"),
    path("orders/", views.PosAwaitingOrdersView.as_view(), name="orders"),
    path(
        "orders/<int:pk>/mark-recorded/",
        views.PosMarkRecordedView.as_view(),
        name="mark_recorded",
    ),
    path("bulk-review/", views.PosBulkReviewView.as_view(), name="bulk_review"),
    path("bulk-not-online/", views.PosBulkNotOnlineView.as_view(), name="bulk_not_online"),
    path("<int:pk>/map/", views.PosConfirmMappingView.as_view(), name="confirm"),
    path("<int:pk>/unmap/", views.PosUnmapView.as_view(), name="unmap"),
    path("<int:pk>/not-online/", views.PosNotOnlineView.as_view(), name="not_online"),
]
