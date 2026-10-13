"""Mounted at ``api/pos/sync/`` by ``config/urls.py``.

All bearer ``SCENT_POS_TOKEN``:

- ``ping/``                      GET
- ``stock/``                     POST — apply a stock snapshot
- ``web-orders/``                GET  — confirmed web orders not yet in the POS
- ``web-orders/<id>/ack/``       POST — mark one recorded in the POS
"""

from __future__ import annotations

from django.urls import URLPattern, path

from . import api_views

app_name = "possync_api"

urlpatterns: list[URLPattern] = [
    path("ping/", api_views.ping, name="ping"),
    path("stock/", api_views.stock, name="stock"),
    path("web-orders/", api_views.web_orders, name="web_orders"),
    path("web-orders/<int:order_id>/ack/", api_views.ack_order, name="ack_order"),
]
