from __future__ import annotations

import pytest

from catalog.factories import CategoryFactory, ProductFactory
from catalog.models import Product


@pytest.mark.django_db
def test_home_shows_featured_products_only(client) -> None:  # type: ignore[no-untyped-def]
    featured = ProductFactory(
        name="Featured Product", is_featured=True, status=Product.Status.PUBLISHED
    )
    ProductFactory(name="Regular Product", is_featured=False, status=Product.Status.PUBLISHED)

    response = client.get("/")

    assert response.status_code == 200
    assert b"Featured Product" in response.content
    assert b"Regular Product" not in response.content
    assert featured in response.context["featured_products"]


@pytest.mark.django_db
def test_home_shows_top_level_published_categories(client) -> None:  # type: ignore[no-untyped-def]
    category = CategoryFactory(name="Fragrances", is_published=True)
    unpublished = CategoryFactory(name="Hidden Category", is_published=False)

    response = client.get("/")

    assert b"Fragrances" in response.content
    assert b"Hidden Category" not in response.content
    assert category in response.context["categories"]
    assert unpublished not in response.context["categories"]
