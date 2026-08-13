"""storefront.views.ProductListView — rendering, sort, pagination, and
Stage 6 gate 5 (assertNumQueries bounded, flat as fixture count grows).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    VariantAttributeValueFactory,
)
from catalog.models import Product

LIST_URL = "/products/"


@pytest.mark.django_db
def test_listing_shows_published_products_and_excludes_drafts(client) -> None:  # type: ignore[no-untyped-def]
    published = ProductFactory(name="Published Product", status=Product.Status.PUBLISHED)
    ProductFactory(name="Draft Product", status=Product.Status.DRAFT)

    response = client.get(LIST_URL)

    assert response.status_code == 200
    assert b"Published Product" in response.content
    assert b"Draft Product" not in response.content
    assert published in response.context["products"]


@pytest.mark.django_db
def test_empty_state_shown_when_no_products_match(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(LIST_URL)
    assert response.status_code == 200
    assert b"No products match" in response.content


@pytest.mark.django_db
def test_category_page_scopes_to_that_category(client) -> None:  # type: ignore[no-untyped-def]
    category = CategoryFactory(name="Fragrances")
    other = CategoryFactory()
    in_category = ProductFactory(category=category, status=Product.Status.PUBLISHED)
    not_in_category = ProductFactory(category=other, status=Product.Status.PUBLISHED)

    response = client.get(f"/category/{category.slug}/")

    assert response.status_code == 200
    assert in_category in response.context["products"]
    assert not_in_category not in response.context["products"]
    assert b"Fragrances" in response.content


@pytest.mark.django_db
def test_brand_query_param_filters_the_listing(client) -> None:  # type: ignore[no-untyped-def]
    nike = BrandFactory()
    match = ProductFactory(brand=nike, status=Product.Status.PUBLISHED)
    other = ProductFactory(status=Product.Status.PUBLISHED)

    response = client.get(LIST_URL, {"brand": nike.slug})

    assert match in response.context["products"]
    assert other not in response.context["products"]


@pytest.mark.django_db
def test_sort_by_price_ascending(client) -> None:  # type: ignore[no-untyped-def]
    expensive = ProductFactory(
        default_variant_price=Decimal("100.00"), status=Product.Status.PUBLISHED
    )
    cheap = ProductFactory(default_variant_price=Decimal("10.00"), status=Product.Status.PUBLISHED)

    response = client.get(LIST_URL, {"sort": "price_asc"})

    products = list(response.context["products"])
    assert products.index(cheap) < products.index(expensive)


@pytest.mark.django_db
def test_pagination_splits_results_across_pages(client) -> None:  # type: ignore[no-untyped-def]
    for _ in range(30):
        ProductFactory(status=Product.Status.PUBLISHED)

    page_one = client.get(LIST_URL)
    page_two = client.get(LIST_URL, {"page": 2})

    assert len(page_one.context["products"]) == 24
    assert len(page_two.context["products"]) == 6


@pytest.mark.django_db
def test_query_count_stays_flat_as_fixture_count_grows_from_5_to_50(client) -> None:  # type: ignore[no-untyped-def]
    """Stage 6 gate 5."""
    client.get(LIST_URL)  # warm up StoreSettings.load(), session/cache tables

    # Brand and an attribute facet with two values, exercised on every
    # fixture, so brand_facet_counts()/attribute_facet_counts() are
    # actually on the hook here too, not just the base product query.
    brand = BrandFactory()
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    blue = AttributeValueFactory(definition=color, value="Blue")

    def _make_product() -> None:
        product = ProductFactory(brand=brand, status=Product.Status.PUBLISHED)
        VariantAttributeValueFactory(
            variant=product.variants.get(), value=red if product.pk % 2 else blue
        )

    for _ in range(5):
        _make_product()
    with CaptureQueriesContext(connection) as captured_at_5:
        response = client.get(LIST_URL)
    assert response.status_code == 200
    queries_at_5 = len(captured_at_5)

    for _ in range(45):
        _make_product()
    assert Product.objects.filter(status=Product.Status.PUBLISHED).count() == 50
    with CaptureQueriesContext(connection) as captured_at_50:
        response = client.get(LIST_URL)
    assert response.status_code == 200
    queries_at_50 = len(captured_at_50)

    assert queries_at_50 == queries_at_5, (
        f"query count grew with fixture count: {queries_at_5} at 5, {queries_at_50} at 50 — "
        "likely an N+1"
    )
