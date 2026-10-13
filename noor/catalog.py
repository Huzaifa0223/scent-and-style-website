"""The ONE place Noor's flat product rows are derived from the catalog.

Every Noor endpoint (public catalogue, public product feed, private tablet
sync) is a projection of ``product_rows()``; nothing else in this app reads
``Product``/``ProductVariant`` fields. If the catalog model changes, this is
the only file to touch.

Field mapping (see also ``docs/noor-integration.md``):

==============  =========================================================
Noor field      Source
==============  =========================================================
slug            ``Product.slug``
name            ``Product.name``
brand           ``Product.brand.name`` ("" when no brand)
category        ``Product.category.name`` (top-level category)
price           representative variant's ``ProductVariant.price``, whole
                rupees, rounded half-up
in_stock        representative variant's ``available_quantity > 0``
stock_qty       representative variant's ``available_quantity``
                (``stock_quantity`` minus live reservations), floored at 0
description     ``Product.short_description``, else ``Product.description``
                with legacy "Top notes: …" lines removed (as the PDP does)
image           primary ``ProductImage`` 600px JPEG derivative (else the
                original), absolute URL; "" when the product has no image
url             ``/product/<slug>/`` on the site's public base URL
notes           ``Product.top_notes`` / ``heart_notes`` / ``base_notes``,
                falling back to labelled lines in ``description``; empty
                lists when the site stores none
==============  =========================================================

Price, stock and the in-stock flag all come from ONE *representative*
variant so a row can never pair one variant's price with another's count:
the default variant when it can be bought, otherwise the first active
variant that can. A product with no active variant has no price to publish
and is omitted rather than shown with an invented one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urljoin

from django.db.models import Prefetch

from catalog.models import Product, ProductImage, ProductVariant
from storefront.views import _split_legacy_fragrance_notes

_NOTE_SEPARATORS = re.compile(r"[,;\n]+")


@dataclass(frozen=True)
class ProductRow:
    """One published product as Noor sees it.

    ``stock_qty`` is ``None`` only when a source knows *whether* an item is
    in stock but not *how many* — the kiosk sync then sends ``inStock``
    without a number instead of guessing one. This store always counts
    units, so ``product_rows()`` never produces ``None`` today; the field
    keeps the sync contract honest if that ever changes.
    """

    slug: str
    name: str
    brand: str
    category: str
    price: int
    in_stock: bool
    stock_qty: int | None
    description: str
    image: str
    url: str
    top_notes: tuple[str, ...]
    heart_notes: tuple[str, ...]
    base_notes: tuple[str, ...]


def product_rows(*, base_url: str) -> list[ProductRow]:
    """Published products as flat rows, ordered by slug (stable for diffing).

    Query shape: one query for products (``brand``/``category`` joined), one
    prefetch for active variants carrying the annotated available quantity,
    one for images — constant regardless of catalog size.

    Args:
        base_url: Public base URL without a trailing slash, e.g.
            ``"https://scentandstyle.pk"``. Used for product URLs and for
            image paths that are not already absolute (object storage).
    """
    products = (
        Product.objects.filter(status=Product.Status.PUBLISHED)
        .select_related("brand", "category")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.with_available_quantity().filter(is_active=True),
            ),
            Prefetch("images", queryset=ProductImage.objects.order_by("position", "id")),
        )
        .order_by("slug")
    )
    rows: list[ProductRow] = []
    for product in products:
        variant = _representative_variant(list(product.variants.all()))
        if variant is None:
            continue
        rows.append(_build_row(product, variant, base_url=base_url))
    return rows


def _available(variant: ProductVariant) -> int:
    # available_quantity is with_available_quantity()'s runtime annotation —
    # django-stubs cannot see it statically.
    return max(int(variant.available_quantity), 0)  # type: ignore[attr-defined]


def _representative_variant(variants: list[ProductVariant]) -> ProductVariant | None:
    if not variants:
        return None
    default = next((v for v in variants if v.is_default), variants[0])
    if _available(default) > 0:
        return default
    return next((v for v in variants if _available(v) > 0), default)


def _build_row(product: Product, variant: ProductVariant, *, base_url: str) -> ProductRow:
    legacy_notes, description_without_notes = _split_legacy_fragrance_notes(product.description)
    available = _available(variant)
    return ProductRow(
        slug=product.slug,
        name=product.name,
        brand=product.brand.name if product.brand is not None else "",
        category=product.category.name,
        price=_whole_rupees(variant.price),
        in_stock=available > 0,
        stock_qty=available,
        description=product.short_description or description_without_notes,
        image=_image_url(list(product.images.all()), base_url=base_url),
        url=f"{base_url}{product.get_absolute_url()}",
        top_notes=_note_list(product.top_notes or legacy_notes.get("top", "")),
        heart_notes=_note_list(product.heart_notes or legacy_notes.get("heart", "")),
        base_notes=_note_list(product.base_notes or legacy_notes.get("base", "")),
    )


def _whole_rupees(amount: Decimal) -> int:
    """Prices are ``Decimal(12,2)``; Noor wants whole rupees. Half-up, not
    Python's banker's ``round()``, so Rs. 8,499.50 is 8,500 as a shopper
    would expect."""
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _note_list(raw: str) -> tuple[str, ...]:
    """Split a free-text note field on commas, semicolons and line breaks.
    Values are passed through untouched — never re-cased, merged or invented."""
    return tuple(part.strip() for part in _NOTE_SEPARATORS.split(raw) if part.strip())


def _image_url(images: list[ProductImage], *, base_url: str) -> str:
    primary = next((image for image in images if image.is_primary), None)
    chosen = primary or (images[0] if images else None)
    if chosen is None:
        return ""
    for field in (chosen.card_jpeg, chosen.image):
        if field:
            return urljoin(f"{base_url}/", field.url)
    return ""
