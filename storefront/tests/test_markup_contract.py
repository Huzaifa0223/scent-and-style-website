"""Structural contracts the storefront polish pass depends on.

These are deliberately about *shape*, not appearance: that every product
renders exactly one tile, that a tile without photography still emits the
ratio-locked media box that keeps the grid's rows even, and that every
top-level region of the page sits inside the shared page shell. Colour
and spacing belong in the token layer and are not asserted here.

Parsed with django.test.html.parse_html via storefront/tests/html_tree.py
— no regular expressions over markup.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test.html import parse_html

from catalog.factories import ProductFactory, ProductImageFactory
from catalog.models import Product
from storefront.tests.html_tree import (
    by_tag,
    classes,
    is_inside,
    with_attr,
    with_class,
)


def _listing(client) -> object:  # type: ignore[no-untyped-def]
    response = client.get("/products/")
    assert response.status_code == 200
    return parse_html(response.content.decode())


@pytest.fixture
def mixed_catalogue() -> list[Product]:
    """Five published products, two with photography and three without.

    The split is the point: the no-image branch is a different template
    path, and it is the one that used to let tile heights drift.
    """
    products = [
        ProductFactory(
            name=f"Product {index}",
            default_variant_price=Decimal("10.00"),
            status=Product.Status.PUBLISHED,
        )
        for index in range(5)
    ]
    for product in products[:2]:
        ProductImageFactory(product=product, is_primary=True)
    return products


@pytest.mark.django_db
def test_listing_renders_exactly_one_card_per_product(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    document = _listing(client)

    assert len(with_class(document, "p-card")) == len(mixed_catalogue) == 5


@pytest.mark.django_db
def test_every_card_has_exactly_one_ratio_locked_media_box(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    """The media box is what makes tile heights uniform — derivatives are
    generated with Pillow's thumbnail(), which preserves each source's own
    ratio, so the CSS box is the only thing holding the grid even. A tile
    that lost its media box would collapse to its caption height."""
    document = _listing(client)

    for card in with_class(document, "p-card"):
        assert len(with_class(card, "p-card__media")) == 1


@pytest.mark.django_db
def test_a_product_without_an_image_still_emits_its_media_box(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    """Height parity is structural, not incidental: the no-image branch
    must still render the box, just with placeholder copy inside it."""
    document = _listing(client)

    cards = with_class(document, "p-card")
    without_image = [card for card in cards if not with_class(card, "p-card__img")]

    assert len(without_image) == 3
    for card in without_image:
        assert len(with_class(card, "p-card__media")) == 1


@pytest.mark.django_db
def test_each_page_region_sits_inside_exactly_one_shell(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    """Guards the gutter contract. Before .shell existed, ten hand-copied
    container strings agreed with each other by luck; the point of the
    class is that an eleventh cannot disagree."""
    document = _listing(client)

    for region in ("header", "main", "footer"):
        element = by_tag(document, region)
        assert len(element) == 1, f"expected exactly one <{region}>"
        assert len(with_class(element[0], "shell")) == 1, f"<{region}> should hold one .shell"


@pytest.mark.django_db
def test_breadcrumb_heading_and_results_all_descend_from_the_main_shell(
    client, mixed_catalogue
) -> None:  # type: ignore[no-untyped-def]
    document = _listing(client)
    main = by_tag(document, "main")[0]
    shell = with_class(main, "shell")[0]

    breadcrumb = with_attr(main, "aria-label", "Breadcrumb")
    heading = by_tag(main, "h1")
    grid = with_class(main, "grid-stagger")

    assert breadcrumb and heading and grid
    for element in (breadcrumb[0], heading[0], grid[0]):
        assert is_inside(element, shell)


@pytest.mark.django_db
def test_the_entrance_stagger_targets_cards_not_raw_child_position(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    """Regression guard for a real defect: each tile renders as *two*
    sibling elements, because the partial emits a JSON-LD <script> before
    its <a>. The stagger therefore counts :nth-of-type scoped to .p-card,
    and any change back to :nth-child would silently put every delay on
    the wrong tile and spend half the budget on invisible script tags.

    Asserted at the markup level, where the interleaving is visible: if a
    future change stops emitting the script, or wraps each card in a div,
    the CSS selector's assumption changes and this should be revisited.
    """
    document = _listing(client)
    grid = with_class(document, "grid-stagger")[0]

    child_tags = [child.name for child in grid.children if hasattr(child, "name")]

    assert child_tags.count("a") == 5
    assert "script" in child_tags, (
        "cards no longer emit a sibling <script>; the stagger's :nth-of-type "
        "scoping in static/css/input.css was chosen for that interleaving"
    )


@pytest.mark.django_db
def test_cards_carry_the_group_marker_the_hover_styles_depend_on(client, mixed_catalogue) -> None:  # type: ignore[no-untyped-def]
    """`group` cannot live in .p-card: it is a marker class with no
    declarations and Tailwind cannot @apply it. The image zoom and price
    colour are group-hover rules, so dropping it from the markup would
    disable both with nothing failing to build."""
    document = _listing(client)

    for card in with_class(document, "p-card"):
        assert "group" in classes(card)
