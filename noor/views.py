"""Noor endpoints: two public read-only feeds and the private tablet sync API.

Every product-shaped response is a projection of ``catalog.product_rows()``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from store.models import StoreSettings

from .catalog import ProductRow, product_rows
from .config import BACKUP_FORMAT, BACKUP_KEEP_NEWEST, BACKUP_MAX_BYTES
from .http import JSON_CONTENT_TYPE, error_response, iso_utc, json_response, public_feed
from .models import KioskBackup
from .security import kiosk_endpoint

logger = logging.getLogger(__name__)


def _base_url(request: HttpRequest) -> str:
    """The site's public base URL, no trailing slash. ``StoreSettings.site_url``
    wins (deterministic, not derived from the Host header); the request's own
    scheme/host is the fallback for a deployment that never configured it."""
    configured = StoreSettings.load().site_url.strip().rstrip("/")
    return configured or request.build_absolute_uri("/").rstrip("/")


def _generated_at() -> str:
    return iso_utc(timezone.now())


# --- public, no token -------------------------------------------------------


def catalog_item(row: ProductRow) -> dict[str, Any]:
    return {"slug": row.slug, "price": row.price, "inStock": row.in_stock, "url": row.url}


def product_item(row: ProductRow) -> dict[str, Any]:
    return {
        "slug": row.slug,
        "name": row.name,
        "brand": row.brand,
        "category": row.category,
        "price": row.price,
        "inStock": row.in_stock,
        "description": row.description,
        "image": row.image,
        "url": row.url,
        "notes": {
            "top": list(row.top_notes),
            "heart": list(row.heart_notes),
            "base": list(row.base_notes),
        },
    }


@public_feed
def catalog_json(request: HttpRequest) -> HttpResponse:
    """GET /api/noor/catalog.json — slug, price, availability, link.

    ``inStock`` is a boolean only; stock counts are never published.
    """
    rows = product_rows(base_url=_base_url(request))
    return json_response(
        {"generatedAt": _generated_at(), "items": [catalog_item(row) for row in rows]}
    )


@public_feed
def products_json(request: HttpRequest) -> HttpResponse:
    """GET /api/noor/products.json — the full public product feed."""
    rows = product_rows(base_url=_base_url(request))
    return json_response(
        {"generatedAt": _generated_at(), "items": [product_item(row) for row in rows]}
    )


# --- private, bearer token --------------------------------------------------


def kiosk_item(row: ProductRow) -> dict[str, Any]:
    """Counted units when we have them; otherwise ``inStock`` alone.

    Never a guessed number: with no count the item carries ``inStock`` (false
    for sold-out items) and no ``stockQty`` key at all.
    """
    if row.stock_qty is None:
        return {"slug": row.slug, "price": row.price, "inStock": row.in_stock}
    return {"slug": row.slug, "price": row.price, "stockQty": row.stock_qty}


@kiosk_endpoint("GET")
def ping(request: HttpRequest) -> HttpResponse:
    return json_response({"ok": True})


@kiosk_endpoint("GET")
def kiosk_catalog(request: HttpRequest) -> HttpResponse:
    rows = product_rows(base_url=_base_url(request))
    return json_response(
        {"generatedAt": _generated_at(), "items": [kiosk_item(row) for row in rows]}
    )


@kiosk_endpoint("POST")
def backup_upload(request: HttpRequest) -> HttpResponse:
    """Store a tablet backup and keep only the newest ``BACKUP_KEEP_NEWEST``.

    The body is read from the stream, not ``request.body``: Django's
    ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB) would turn a legitimate 3-5 MB
    backup into a 400, and raising it would loosen the limit for every
    other form on the site. One byte over the cap is read so "exactly at
    the cap" and "over it" are distinguishable without buffering more.
    """
    declared = request.META.get("CONTENT_LENGTH", "")
    if declared.isdigit() and int(declared) > BACKUP_MAX_BYTES:
        return error_response(413, "payload_too_large")
    raw = request.read(BACKUP_MAX_BYTES + 1)
    if len(raw) > BACKUP_MAX_BYTES:
        return error_response(413, "payload_too_large")

    try:
        text = raw.decode("utf-8")
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError, RecursionError):
        # RecursionError: a few MB of "[[[[…" is valid-looking and would
        # otherwise surface as a 500.
        return error_response(400, "invalid_json")
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        return error_response(400, "invalid_format")

    with transaction.atomic():
        backup = KioskBackup.objects.create(size=len(raw), body=text)
        keep = list(KioskBackup.objects.values_list("pk", flat=True)[:BACKUP_KEEP_NEWEST])
        KioskBackup.objects.exclude(pk__in=keep).delete()
    logger.info("Stored kiosk backup %s (%d bytes).", backup.pk, backup.size)
    return json_response({"storedAt": iso_utc(backup.received_at)}, status=201)


@kiosk_endpoint("GET")
def backup_latest(request: HttpRequest) -> HttpResponse:
    latest = KioskBackup.objects.only("body").first()
    if latest is None:
        return error_response(404, "not_found")
    return HttpResponse(latest.body, content_type=JSON_CONTENT_TYPE)
