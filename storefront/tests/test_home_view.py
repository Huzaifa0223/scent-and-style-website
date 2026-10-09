from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.factories import BrandFactory, CategoryFactory, ProductFactory
from catalog.models import Product

HOME_URL = "/"


@pytest.mark.django_db
def test_home_shows_featured_products_only(client) -> None:  # type: ignore[no-untyped-def]
    featured = ProductFactory(
        name="Featured Product", is_featured=True, status=Product.Status.PUBLISHED
    )
    ProductFactory(name="Regular Product", is_featured=False, status=Product.Status.PUBLISHED)

    response = client.get("/")

    assert response.status_code == 200
    assert featured in response.context["featured_products"]
    assert "Regular Product" not in [p.name for p in response.context["featured_products"]]


@pytest.mark.django_db
def test_home_new_arrivals_includes_every_published_product_newest_first(client) -> None:  # type: ignore[no-untyped-def]
    older = ProductFactory(name="Older Arrival", status=Product.Status.PUBLISHED)
    newer = ProductFactory(name="Newer Arrival", status=Product.Status.PUBLISHED)
    ProductFactory(name="Draft Product", status=Product.Status.DRAFT)

    response = client.get("/")

    assert response.status_code == 200
    arrivals = list(response.context["new_arrivals"])
    assert arrivals.index(newer) < arrivals.index(older)
    assert "Draft Product" not in [p.name for p in arrivals]
    assert b"New arrivals" in response.content  # storefront redesign uses sentence case


@pytest.mark.django_db
def test_home_new_arrivals_empty_state(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/")

    assert response.status_code == 200
    assert b"No products yet" in response.content


@pytest.mark.django_db
def test_home_shows_top_level_published_categories(client) -> None:  # type: ignore[no-untyped-def]
    category = CategoryFactory(name="Fragrances", is_published=True)
    unpublished = CategoryFactory(name="Hidden Category", is_published=False)

    response = client.get("/")

    assert b"Fragrances" in response.content
    assert b"Hidden Category" not in response.content
    assert category in response.context["categories"]
    assert unpublished not in response.context["categories"]


@pytest.mark.django_db
def test_home_shows_published_brands_with_clickable_product_filters(client) -> None:  # type: ignore[no-untyped-def]
    brand = BrandFactory(name="Afnan", is_published=True)
    ProductFactory(brand=brand, status=Product.Status.PUBLISHED)
    hidden_brand = BrandFactory(name="Hidden brand", is_published=False)
    ProductFactory(brand=hidden_brand, status=Product.Status.PUBLISHED)
    no_live_products = BrandFactory(name="Out of stock brand", is_published=True)
    ProductFactory(brand=no_live_products, status=Product.Status.DRAFT)

    response = client.get(HOME_URL)

    assert response.status_code == 200
    assert brand in response.context["brands"]
    assert hidden_brand not in response.context["brands"]
    assert no_live_products not in response.context["brands"]
    assert f"/products/?brand={brand.slug}".encode() in response.content
    assert b'href="/brands/"' in response.content
    assert b"group-hover:opacity-100" in response.content
    assert b">Afnan</span>" in response.content
    assert b">Explore Afnan</span>" not in response.content


@pytest.mark.django_db
def test_brand_directory_lists_published_brands_with_live_products(client) -> None:  # type: ignore[no-untyped-def]
    brand = BrandFactory(name="Afnan", is_published=True)
    ProductFactory(brand=brand, status=Product.Status.PUBLISHED)
    unpublished_brand = BrandFactory(name="Hidden brand", is_published=False)
    ProductFactory(brand=unpublished_brand, status=Product.Status.PUBLISHED)
    no_live_products = BrandFactory(name="Draft only", is_published=True)
    ProductFactory(brand=no_live_products, status=Product.Status.DRAFT)

    response = client.get("/brands/")

    assert response.status_code == 200
    assert list(response.context["brands"]) == [brand]
    assert b"Afnan" in response.content
    assert b"Hidden brand" not in response.content
    assert b"Draft only" not in response.content
    assert f"/products/?brand={brand.slug}".encode() in response.content
    assert b"group-hover:opacity-100" in response.content


@pytest.mark.django_db
def test_home_includes_the_search_box(client) -> None:  # type: ignore[no-untyped-def]
    """storefront/base.html's storefront_search block, empty since Stage 5,
    now includes search/_search_input.html on every storefront page."""
    response = client.get("/")

    assert response.status_code == 200
    assert b'hx-get="/search/suggest/"' in response.content
    assert b'rel="icon" href="/static/favicon.ico?v=' in response.content
    assert b'href="https://web.facebook.com/ScentnStylePak"' in response.content


@pytest.mark.django_db
def test_query_count_stays_flat_as_fixture_count_grows_from_5_to_50(client) -> None:  # type: ignore[no-untyped-def]
    """Stage 6 gate 5 / §36 — two rails (featured, new arrivals), each with
    its own with_pricing() + primary-image Prefetch(); neither had a
    regression guard before this test."""
    client.get(HOME_URL)  # warm up StoreSettings.load(), session/cache tables

    def _make_product() -> None:
        ProductFactory(is_featured=True, status=Product.Status.PUBLISHED)

    for _ in range(5):
        _make_product()
    with CaptureQueriesContext(connection) as captured_at_5:
        response = client.get(HOME_URL)
    assert response.status_code == 200
    queries_at_5 = len(captured_at_5)

    for _ in range(45):
        _make_product()
    assert Product.objects.filter(status=Product.Status.PUBLISHED).count() == 50
    with CaptureQueriesContext(connection) as captured_at_50:
        response = client.get(HOME_URL)
    assert response.status_code == 200
    queries_at_50 = len(captured_at_50)

    assert queries_at_50 == queries_at_5, (
        f"query count grew with fixture count: {queries_at_5} at 5, {queries_at_50} at 50 — "
        "likely an N+1"
    )
