"""Structured data (§34, roadmap Stage 12) — the one place that builds a
JSON-LD payload for this project. Every function here is pure given its
explicit inputs (no querying, no prefetch assumptions of its own) so a
caller controls exactly what's already loaded — see the module docstring
in ``storefront/views.py`` callers for why that matters: the product-
listing page and the PDP prefetch images differently (``primary_image_
list`` vs the full ``images`` manager), and a function that reached into
``product.images.all()`` itself would silently N+1 on whichever page
didn't happen to prefetch under that exact name.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from catalog.models import Product, ProductImage


def product_json_ld(
    product: Product, *, request: HttpRequest, primary_image: ProductImage | None, currency: str
) -> dict[str, Any] | None:
    """§34: "offers... driven off the default variant" — always a single
    ``Offer`` priced off ``product.default_variant``, never an
    ``AggregateOffer`` reflecting the product's full price range. This is
    why the same markup validates whether or not the product has a price
    range (roadmap Stage 12 gate 1): the offer only ever describes one
    variant, and nothing here looks at whether any other variant's price
    differs from it.

    Returns ``None`` for a product with no variants at all — shouldn't
    happen given the catalog's own "every product has >=1 variant"
    invariant, but a caller checking for ``None`` is cheaper than a
    template guessing what an ``offers`` block with no price would even
    mean; schema.org requires ``price`` whenever ``offers`` is present.

    ``currency`` is an explicit parameter, not loaded here via
    ``StoreSettings.load()`` — this project's cache is the *database*
    cache backend (no Redis), so ``cache.get()`` is a real SQL query, not
    a free in-process hit. A caller building JSON-LD once per card on a
    listing page must load ``StoreSettings`` exactly once and pass the
    currency through; calling ``.load()`` inside this function would
    silently reintroduce one query per card — the actual mechanism
    behind the N+1 the human warned about before this function was
    written this way, caught by re-running the Stage 6 listing/home
    ``assertNumQueries`` guards immediately after wiring this in, not
    discovered later.
    """
    variant = product.default_variant
    if variant is None:
        return None

    product_url = request.build_absolute_uri(product.get_absolute_url())
    data: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": product.name,
        "sku": variant.sku,
        "url": product_url,
        "offers": {
            "@type": "Offer",
            "price": str(variant.price),
            "priceCurrency": currency,
            "availability": (
                "https://schema.org/InStock"
                if variant.available_quantity > 0  # type: ignore[attr-defined]
                else "https://schema.org/OutOfStock"
            ),
            "url": product_url,
        },
    }
    if product.short_description:
        data["description"] = product.short_description
    if primary_image is not None:
        data["image"] = request.build_absolute_uri(primary_image.full_webp.url)
    return data


def breadcrumb_json_ld(*, request: HttpRequest, items: list[tuple[str, str]]) -> dict[str, Any]:
    """``items`` is an ordered ``(name, url)`` list, home first."""
    return {
        "@context": "https://schema.org/",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": name,
                "item": request.build_absolute_uri(url),
            }
            for index, (name, url) in enumerate(items, start=1)
        ],
    }
