"""Mounted at ``api/`` by ``config/urls.py``.

Public, no token:

- ``/api/noor/catalog.json``
- ``/api/noor/products.json``

Private, ``Authorization: Bearer <SCENT_SYNC_TOKEN>``:

- ``/api/kiosk/sync/ping/``
- ``/api/kiosk/sync/catalog/``
- ``/api/kiosk/sync/backup/`` (POST)
- ``/api/kiosk/sync/backup/latest/``
"""

from __future__ import annotations

from django.urls import URLPattern, path

from . import views

app_name = "noor"

urlpatterns: list[URLPattern] = [
    path("noor/catalog.json", views.catalog_json, name="catalog"),
    path("noor/products.json", views.products_json, name="products"),
    path("kiosk/sync/ping/", views.ping, name="kiosk_ping"),
    path("kiosk/sync/catalog/", views.kiosk_catalog, name="kiosk_catalog"),
    path("kiosk/sync/backup/", views.backup_upload, name="kiosk_backup"),
    path("kiosk/sync/backup/latest/", views.backup_latest, name="kiosk_backup_latest"),
]
