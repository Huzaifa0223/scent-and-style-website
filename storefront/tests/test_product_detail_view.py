"""storefront.views.ProductDetailView — Stage 6 gates 3 and 4: the variant
selector's data is present and correct so price/availability/gallery can
update client-side without a reload, and an out-of-stock variant is
labelled specifically, not generically.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    ProductFactory,
    ProductVariantFactory,
    VariantAttributeValueFactory,
)
from catalog.models import Product


@pytest.mark.django_db
def test_pdp_renders_the_product_name_and_price(client) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(
        name="Afnan 9PM Eau de Parfum",
        default_variant_price=Decimal("25.00"),
        status=Product.Status.PUBLISHED,
    )

    response = client.get(f"/product/{product.slug}/")

    assert response.status_code == 200
    assert b"Afnan 9PM Eau de Parfum" in response.content


@pytest.mark.django_db
def test_pdp_404s_for_an_unpublished_product(client) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(status=Product.Status.DRAFT)

    response = client.get(f"/product/{product.slug}/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_pdp_exposes_every_variant_with_price_and_availability_for_the_selector(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """Gate 3: the client-side selector needs each variant's price and
    availability up front — there's no reload to fetch it on selection."""
    size = AttributeDefinitionFactory(is_variant_option=True)
    small = AttributeValueFactory(definition=size, value="50ml")
    large = AttributeValueFactory(definition=size, value="100ml")
    product = ProductFactory(
        default_variant_price=Decimal("25.00"), status=Product.Status.PUBLISHED
    )
    default_variant = product.variants.get()
    default_variant.stock_quantity = 10
    default_variant.save(update_fields=["stock_quantity", "updated_at"])
    VariantAttributeValueFactory(variant=default_variant, value=small)
    out_of_stock = ProductVariantFactory(product=product, price=Decimal("30.00"), stock_quantity=0)
    VariantAttributeValueFactory(variant=out_of_stock, value=large)

    response = client.get(f"/product/{product.slug}/")

    by_id = {row["id"]: row for row in response.context["variants_data"]}
    assert by_id[default_variant.pk]["price"] == "25.00"
    assert by_id[default_variant.pk]["available_quantity"] == 10
    assert by_id[out_of_stock.pk]["price"] == "30.00"
    assert by_id[out_of_stock.pk]["available_quantity"] == 0
    assert b"Out of stock" in response.content or b"Out of Stock" in response.content


@pytest.mark.django_db
def test_pdp_labels_variant_options_with_their_full_attribute_combination(
    client,
) -> None:  # type: ignore[no-untyped-def]
    # The selector only renders with 2+ variants -- a single-variant
    # product needs no selector at all, so this needs a second variant to
    # exercise the labelling.
    color = AttributeDefinitionFactory(is_variant_option=True)
    red = AttributeValueFactory(definition=color, value="Red")
    blue = AttributeValueFactory(definition=color, value="Blue")
    product = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=product.variants.get(), value=red)
    VariantAttributeValueFactory(
        variant=ProductVariantFactory(product=product, price=Decimal("30.00")), value=blue
    )

    response = client.get(f"/product/{product.slug}/")

    assert b"Red" in response.content
    assert b"Blue" in response.content


@pytest.mark.django_db
def test_pdp_default_variant_is_the_products_designated_default(client) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(status=Product.Status.PUBLISHED)
    default_variant = product.variants.get()
    ProductVariantFactory(product=product, price=Decimal("99.00"))

    response = client.get(f"/product/{product.slug}/")

    assert response.context["default_variant"].pk == default_variant.pk
