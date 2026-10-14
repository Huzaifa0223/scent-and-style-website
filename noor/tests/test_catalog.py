"""noor.catalog.product_rows — the one mapping from our catalog to Noor rows."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.factories import BrandFactory, ProductImageFactory, ProductVariantFactory
from catalog.models import Product
from inventory.models import StockReservation
from noor.catalog import product_rows
from noor.tests.support import published
from orders.factories import OrderFactory
from store.models import StoreSettings

BASE = "https://scentandstyle.pk"


def _rows():  # type: ignore[no-untyped-def]
    return product_rows(base_url=BASE)


@pytest.mark.django_db
def test_only_published_products_are_included() -> None:
    published("Live One")
    published("Draft One", status=Product.Status.DRAFT)
    published("Archived One", status=Product.Status.ARCHIVED)

    assert [row.name for row in _rows()] == ["Live One"]


@pytest.mark.django_db
def test_row_maps_slug_name_brand_category_url_and_description() -> None:
    brand = BrandFactory(name="Lattafa")
    product = published("Khamrah", brand=brand, short_description="Eau de Parfum (EDP) 100ml")

    (row,) = _rows()

    assert row.slug == product.slug
    assert row.name == "Khamrah"
    assert row.brand == "Lattafa"
    assert row.category == product.category.name
    assert row.url == f"{BASE}/product/{product.slug}/"
    assert row.description == "Eau de Parfum (EDP) 100ml"


@pytest.mark.django_db
def test_missing_brand_is_an_empty_string() -> None:
    published("No Brand")

    assert _rows()[0].brand == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("price", "expected"),
    [("8500.00", 8500), ("8499.50", 8500), ("8499.49", 8499), ("0.50", 1)],
)
def test_price_is_whole_rupees_rounded_half_up(price: str, expected: int) -> None:
    published(price=price)

    assert _rows()[0].price == expected


@pytest.mark.django_db
def test_stock_is_the_counted_available_quantity() -> None:
    published(stock=7)

    (row,) = _rows()

    assert row.stock_qty == 7
    assert row.in_stock is True


@pytest.mark.django_db
def test_live_reservations_are_subtracted_from_the_count() -> None:
    product = published(stock=5)
    StockReservation.objects.create(
        variant=product.variants.get(),
        order=OrderFactory(),
        quantity=2,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    assert _rows()[0].stock_qty == 3


@pytest.mark.django_db
def test_sold_out_product_is_listed_with_zero_and_not_in_stock() -> None:
    published(stock=0)

    (row,) = _rows()

    assert row.stock_qty == 0
    assert row.in_stock is False


@pytest.mark.django_db
def test_sold_out_default_falls_back_to_the_first_buyable_variant() -> None:
    product = published(price="9000.00", stock=0)
    ProductVariantFactory(product=product, price=Decimal("4500.00"), stock_quantity=3)

    (row,) = _rows()

    # One coherent variant: the 4,500 price comes with the 3 units that exist.
    assert (row.price, row.stock_qty, row.in_stock) == (4500, 3, True)


@pytest.mark.django_db
def test_buyable_default_variant_wins_over_cheaper_siblings() -> None:
    product = published(price="9000.00", stock=2)
    ProductVariantFactory(product=product, price=Decimal("4500.00"), stock_quantity=10)

    (row,) = _rows()

    assert (row.price, row.stock_qty) == (9000, 2)


@pytest.mark.django_db
def test_inactive_variants_are_ignored_and_a_product_without_any_is_omitted() -> None:
    product = published()
    product.variants.update(is_active=False)

    assert _rows() == []


@pytest.mark.django_db
def test_structured_notes_are_split_and_never_invented() -> None:
    published(
        "With Notes",
        top_notes="Bergamot, Saffron",
        heart_notes="Dates;Rose\nOud",
        base_notes="",
    )

    (row,) = _rows()

    assert row.top_notes == ("Bergamot", "Saffron")
    assert row.heart_notes == ("Dates", "Rose", "Oud")
    assert row.base_notes == ()


@pytest.mark.django_db
def test_labelled_lines_in_a_legacy_description_become_notes() -> None:
    published(
        "Legacy",
        description="Top notes: Lemon, Mint\nBase notes: Musk\nA fresh daily scent.",
    )

    (row,) = _rows()

    assert row.top_notes == ("Lemon", "Mint")
    assert row.heart_notes == ()
    assert row.base_notes == ("Musk",)
    # Same as the product page: the note lines are not repeated in the text.
    assert row.description == "A fresh daily scent."


@pytest.mark.django_db
def test_image_is_the_primary_jpeg_derivative_as_an_absolute_url(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    product = published()
    ProductImageFactory(product=product)

    (row,) = _rows()

    assert row.image.startswith(f"{BASE}/media/products/card/")
    assert row.image.endswith(".jpg")


@pytest.mark.django_db
def test_product_without_an_image_has_an_empty_image_string() -> None:
    published()

    assert _rows()[0].image == ""


@pytest.mark.django_db
def test_query_count_does_not_grow_with_the_catalog(django_assert_max_num_queries) -> None:  # type: ignore[no-untyped-def]
    for index in range(12):
        published(f"Perfume {index}", brand=BrandFactory())
    StoreSettings.load()  # warm up the cached singleton (the default lead time)

    with django_assert_max_num_queries(4):
        assert len(_rows()) == 12
