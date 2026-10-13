"""Shared helpers for the noor tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from catalog.factories import ProductFactory
from catalog.models import Product

# Deliberately fake, but long enough (>= 32) to be accepted as a real token.
TOKEN = "unit-test-token-" + "x" * 32

CATALOG_URL = "/api/noor/catalog.json"
PRODUCTS_URL = "/api/noor/products.json"
PING_URL = "/api/kiosk/sync/ping/"
KIOSK_CATALOG_URL = "/api/kiosk/sync/catalog/"
BACKUP_URL = "/api/kiosk/sync/backup/"
LATEST_URL = "/api/kiosk/sync/backup/latest/"

PRIVATE_GET_URLS = (PING_URL, KIOSK_CATALOG_URL, LATEST_URL)


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def published(
    name: str = "Khamrah",
    *,
    price: str = "8500.00",
    stock: int = 4,
    status: str = Product.Status.PUBLISHED,
    **fields: Any,
) -> Product:
    """A product with one active default variant holding ``stock`` units."""
    product = ProductFactory(
        name=name, status=status, default_variant_price=Decimal(price), **fields
    )
    product.variants.update(stock_quantity=stock)
    return product


def backup_body(total_bytes: int) -> bytes:
    """A valid backup of exactly ``total_bytes`` bytes."""
    prefix = b'{"format":"scent-style-backup","pad":"'
    suffix = b'"}'
    return prefix + b"a" * (total_bytes - len(prefix) - len(suffix)) + suffix
