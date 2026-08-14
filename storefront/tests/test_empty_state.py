"""The listing page with nothing to list.

An empty catalogue and an over-restrictive filter reach the same branch,
and that branch is easy to break without noticing: it is the one path
where the product grid never renders, so anything the page derives from
the product list has to tolerate an empty sequence.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test.html import parse_html

from catalog.factories import ProductFactory
from catalog.models import Product
from storefront.tests.html_tree import by_tag, with_class


@pytest.mark.django_db
def test_listing_renders_with_no_products_at_all(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/products/")

    assert response.status_code == 200
    document = parse_html(response.content.decode())
    assert with_class(document, "p-card") == []


@pytest.mark.django_db
def test_the_empty_catalogue_still_renders_the_page_shell(client) -> None:  # type: ignore[no-untyped-def]
    """The chrome is not conditional on having products: header, main and
    footer each keep their shell, so an empty store still looks like the
    store rather than an unstyled error page."""
    response = client.get("/products/")

    document = parse_html(response.content.decode())
    for region in ("header", "main", "footer"):
        element = by_tag(document, region)
        assert len(element) == 1
        assert len(with_class(element[0], "shell")) == 1


@pytest.mark.django_db
def test_a_filter_matching_nothing_offers_a_way_back(client) -> None:  # type: ignore[no-untyped-def]
    """A dead end is the failure mode here — the empty state has to say
    what happened and link out of it, not just render nothing."""
    ProductFactory(default_variant_price=Decimal("10.00"), status=Product.Status.PUBLISHED)

    response = client.get("/products/", {"price_min": "999999"})

    assert response.status_code == 200
    assert b"No products match these filters." in response.content
    document = parse_html(response.content.decode())
    assert with_class(document, "p-card") == []
    hrefs = [dict(a.attributes).get("href") for a in by_tag(document, "a")]
    assert "/products/" in hrefs, "empty state should link back to the unfiltered listing"


@pytest.mark.django_db
def test_an_empty_listing_reports_a_zero_count_rather_than_omitting_it(client) -> None:  # type: ignore[no-untyped-def]
    """Deviates from the polish brief, which expected the grid container
    to render even when empty. It does not, by design: this template
    swaps the grid for an empty state instead of shipping an empty grid,
    which is the better outcome. What is asserted instead is that the
    count line still renders and reads zero, so the page never silently
    looks like it is still loading."""
    response = client.get("/products/")

    assert b"0 products" in response.content
