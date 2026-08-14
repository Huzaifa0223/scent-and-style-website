"""storefront.seo — JSON-LD structural validation (roadmap Stage 12 gate
1: "JSON-LD validates against a schema validator for a product with and
without a price range").

No offline schema.org/JSON-LD validator library is in this project's
approved dependency list, and a real validator (Google's Rich Results
Test, schema.org's own validator) needs a publicly reachable URL this
dev environment doesn't have — the same class of check §35 already
treats as a live, human task ("verify against Facebook's sharing
debugger"), not something an automated test can do offline. What *is*
automated here: a thorough structural check against schema.org's own
documented Product/Offer/BreadcrumbList requirements (every required
property present, correctly typed, and the whole payload round-trips
through real JSON parsing after going through this project's own
``ld_json`` escaping filter) — real validation of everything that can be
checked without a live URL. The live-validator pass itself is recorded
in specs/state.md under Human tasks, not silently skipped.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.db.models import Prefetch
from django.test import RequestFactory

from catalog.factories import ProductFactory, ProductImageFactory, ProductVariantFactory
from catalog.models import Product, ProductVariant
from core.templatetags.jsonld import ld_json
from storefront import seo

_VALID_AVAILABILITY = {"https://schema.org/InStock", "https://schema.org/OutOfStock"}


def _reload_with_available_quantity(product: Product) -> Product:
    """product.default_variant needs variant.available_quantity, which
    only exists when variants were fetched via with_available_quantity()
    — the same prefetch shape every real caller (ProductDetailView,
    ProductListView) already uses. A bare ProductFactory()/`.variants.
    get()` round-trip doesn't have it, so tests calling seo.product_json_ld()
    directly must reload through this shape first, same as production."""
    return Product.objects.prefetch_related(
        Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity())
    ).get(pk=product.pk)


def _assert_valid_product_json_ld(data: dict[str, object]) -> None:
    """Schema.org's own Product + Offer requirements, checked directly —
    see https://schema.org/Product and https://schema.org/Offer, and
    Google's own "required properties" list for Product rich results
    (name, offers.price, offers.priceCurrency, offers.availability)."""
    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "Product"
    assert isinstance(data["name"], str) and data["name"]
    assert isinstance(data["url"], str) and data["url"].startswith("http")

    offers = data["offers"]
    assert isinstance(offers, dict)
    assert offers["@type"] == "Offer"
    assert isinstance(offers["price"], str)
    Decimal(offers["price"])  # must parse as a real decimal, not just "be a string"
    assert isinstance(offers["priceCurrency"], str) and len(offers["priceCurrency"]) == 3
    assert offers["availability"] in _VALID_AVAILABILITY
    assert isinstance(offers["url"], str) and offers["url"].startswith("http")

    # Round-trips through real JSON parsing after the same escaping the
    # template applies — proves ld_json() doesn't corrupt the payload.
    rendered = str(ld_json(data))
    reparsed = json.loads(rendered)
    assert reparsed == data


@pytest.mark.django_db
def test_gate1_product_json_ld_validates_for_a_product_without_a_price_range() -> None:
    product = ProductFactory(
        name="Single-Price Product",
        default_variant_price=Decimal("500.00"),
        status=Product.Status.PUBLISHED,
    )
    variant = product.variants.get()
    variant.stock_quantity = 5
    variant.save(update_fields=["stock_quantity", "updated_at"])
    product = _reload_with_available_quantity(product)
    request = RequestFactory().get(f"/product/{product.slug}/")

    data = seo.product_json_ld(product, request=request, primary_image=None, currency="PKR")

    assert data is not None
    _assert_valid_product_json_ld(data)
    assert data["offers"]["price"] == "500.00"
    assert data["offers"]["availability"] == "https://schema.org/InStock"


@pytest.mark.django_db
def test_gate1_product_json_ld_validates_for_a_product_with_a_price_range() -> None:
    """The same markup shape must stay valid when the product has
    multiple variants at different prices — offers is always priced off
    the default variant alone (storefront.seo's own module docstring),
    so nothing here should change shape just because other variants
    exist at other prices."""
    product = ProductFactory(
        name="Price-Range Product",
        default_variant_price=Decimal("500.00"),
        status=Product.Status.PUBLISHED,
    )
    default_variant = product.variants.get()
    default_variant.stock_quantity = 5
    default_variant.save(update_fields=["stock_quantity", "updated_at"])
    ProductVariantFactory(product=product, price=Decimal("750.00"), stock_quantity=5)
    ProductVariantFactory(product=product, price=Decimal("1000.00"), stock_quantity=0)
    product = _reload_with_available_quantity(product)
    request = RequestFactory().get(f"/product/{product.slug}/")

    data = seo.product_json_ld(product, request=request, primary_image=None, currency="PKR")

    assert data is not None
    _assert_valid_product_json_ld(data)
    # Priced off the default variant specifically, not the range's min/max.
    assert data["offers"]["price"] == "500.00"


@pytest.mark.django_db
def test_product_json_ld_returns_none_for_a_product_with_no_variants() -> None:
    """Shouldn't happen given the catalog's own "every product has >=1
    variant" invariant, but product_json_ld() checks for it explicitly
    rather than letting a template guess what an empty offers block
    means — simulated here via an empty variants prefetch, the same
    mechanism a real (invariant-violating) product would hit."""
    product = ProductFactory(status=Product.Status.PUBLISHED)
    product = Product.objects.prefetch_related(
        Prefetch("variants", queryset=ProductVariant.objects.none())
    ).get(pk=product.pk)
    request = RequestFactory().get(f"/product/{product.slug}/")

    data = seo.product_json_ld(product, request=request, primary_image=None, currency="PKR")

    assert data is None


@pytest.mark.django_db
def test_product_json_ld_includes_the_short_description_when_set() -> None:
    product = ProductFactory(
        status=Product.Status.PUBLISHED, short_description="A genuinely short description."
    )
    variant = product.variants.get()
    variant.stock_quantity = 1
    variant.save(update_fields=["stock_quantity", "updated_at"])
    product = _reload_with_available_quantity(product)
    request = RequestFactory().get(f"/product/{product.slug}/")

    data = seo.product_json_ld(product, request=request, primary_image=None, currency="PKR")

    assert data is not None
    assert data["description"] == "A genuinely short description."


@pytest.mark.django_db
def test_product_json_ld_includes_a_valid_image_url_when_a_primary_image_exists() -> None:
    product = ProductFactory(status=Product.Status.PUBLISHED)
    variant = product.variants.get()
    variant.stock_quantity = 1
    variant.save(update_fields=["stock_quantity", "updated_at"])
    image = ProductImageFactory(product=product, is_primary=True)
    product = _reload_with_available_quantity(product)
    request = RequestFactory().get(f"/product/{product.slug}/")

    data = seo.product_json_ld(product, request=request, primary_image=image, currency="PKR")

    assert data is not None
    assert isinstance(data["image"], str)
    assert data["image"].startswith("http")


@pytest.mark.django_db
def test_gate1_breadcrumb_json_ld_validates() -> None:
    """https://schema.org/BreadcrumbList: itemListElement is an ordered
    list of ListItem entries, each with a 1-based position, a name, and
    an item URL."""
    request = RequestFactory().get("/product/example/")

    data = seo.breadcrumb_json_ld(
        request=request,
        items=[("Home", "/"), ("Category", "/category/example/"), ("Product", "/product/example/")],
    )

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "BreadcrumbList"
    items = data["itemListElement"]
    assert isinstance(items, list)
    assert len(items) == 3
    for index, item in enumerate(items, start=1):
        assert item["@type"] == "ListItem"
        assert item["position"] == index
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["item"], str) and item["item"].startswith("http")

    rendered = str(ld_json(data))
    assert json.loads(rendered) == data
