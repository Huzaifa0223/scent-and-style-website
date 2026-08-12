"""catalog.models.ProductVariantQuerySet.with_available_quantity() aggregates
over StockReservation, a to-many reverse FK from ProductVariant. Combined
with ANOTHER to-many join in the same queryset — variant_attribute_values
here, or whatever Stage 6's listing page joins later — two to-many tables
joined into one query multiply rows before GROUP BY collapses them back
down, so a naive Sum() would overcount. This is exactly why that method
uses a correlated Subquery instead of a Sum(..., filter=) join-based
aggregate; these tests are what proved the join-based form was wrong
before it shipped, and guard against it coming back in a future edit.
"""

from __future__ import annotations

import pytest
from django.db.models import Count, Prefetch

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    ProductFactory,
    ProductVariantFactory,
    VariantAttributeValueFactory,
)
from catalog.models import Product, ProductVariant
from inventory.factories import StockReservationFactory


@pytest.mark.django_db
def test_with_available_quantity_does_not_fan_out_with_a_variant_attribute_join() -> None:
    """2 active reservations x 2 attribute values = 4 joined rows before
    aggregation if both relations are joined in one query — a join-based
    Sum() would read reserved_quantity as 10 (5 x 2), not 5."""
    variant = ProductVariantFactory(stock_quantity=10)
    StockReservationFactory(variant=variant, quantity=3)
    StockReservationFactory(variant=variant, quantity=2)

    color = AttributeDefinitionFactory(is_variant_option=True)
    red = AttributeValueFactory(definition=color, value="Red")
    blue = AttributeValueFactory(definition=color, value="Blue")
    VariantAttributeValueFactory(variant=variant, value=red)
    VariantAttributeValueFactory(variant=variant, value=blue)

    annotated = (
        ProductVariant.objects.with_available_quantity()
        .annotate(attribute_value_count=Count("variant_attribute_values"))
        .get(pk=variant.pk)
    )

    assert annotated.attribute_value_count == 2  # confirms the second join is really active
    assert annotated.reserved_quantity == 5
    assert annotated.available_quantity == 5


@pytest.mark.django_db
def test_with_available_quantity_does_not_fan_out_across_multiple_variants_and_reservations() -> (
    None
):
    """The same risk restated with several variants and an uneven number
    of reservations each, so a fan-out couldn't hide behind every variant
    happening to have the same multiplier."""
    product = ProductFactory()
    first = product.variants.get()
    first.stock_quantity = 20
    first.save(update_fields=["stock_quantity", "updated_at"])
    second = ProductVariantFactory(product=product, stock_quantity=15)

    StockReservationFactory(variant=first, quantity=1)
    StockReservationFactory(variant=first, quantity=2)
    StockReservationFactory(variant=first, quantity=3)
    StockReservationFactory(variant=second, quantity=4)

    color = AttributeDefinitionFactory(is_variant_option=True)
    for label in ("Red", "Green", "Blue"):
        value = AttributeValueFactory(definition=color, value=label)
        VariantAttributeValueFactory(variant=first, value=value)
    VariantAttributeValueFactory(variant=second, value=AttributeValueFactory(definition=color))

    annotated = {
        row.pk: row
        for row in ProductVariant.objects.with_available_quantity()
        .annotate(attribute_value_count=Count("variant_attribute_values"))
        .filter(pk__in=[first.pk, second.pk])
    }

    assert annotated[first.pk].attribute_value_count == 3
    assert annotated[first.pk].reserved_quantity == 6
    assert annotated[first.pk].available_quantity == 14

    assert annotated[second.pk].attribute_value_count == 1
    assert annotated[second.pk].reserved_quantity == 4
    assert annotated[second.pk].available_quantity == 11


@pytest.mark.django_db
def test_the_safe_pattern_for_combining_with_pricing_and_with_available_quantity() -> None:
    """with_pricing() (Product) and with_available_quantity() (ProductVariant)
    can't literally be chained on one queryset — they annotate different
    models. The safe way to combine them, and the one Stage 6's listing
    page should use, is Prefetch: it runs as its own query, so it can
    never fan out against with_pricing()'s own variants__price aggregate.
    Documented here as a working example, not just a warning."""
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])
    StockReservationFactory(variant=variant, quantity=4)

    fetched = (
        Product.objects.with_pricing()
        .prefetch_related(
            Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity())
        )
        .get(pk=product.pk)
    )

    assert fetched.display_price is not None  # with_pricing()'s own annotation, unaffected
    (fetched_variant,) = fetched.variants.all()
    assert fetched_variant.available_quantity == 6
