from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    ProductFactory,
    ProductVariantFactory,
)
from catalog.models import AttributeValue, ProductVariant, VariantAttributeValue


@pytest.mark.django_db
def test_discount_percent_none_when_no_compare_at_price() -> None:
    variant = ProductVariantFactory(price=Decimal("100.00"), compare_at_price=None)
    assert variant.discount_percent is None


@pytest.mark.django_db
def test_discount_percent_none_when_compare_at_price_not_higher() -> None:
    variant = ProductVariantFactory(price=Decimal("100.00"), compare_at_price=Decimal("100.00"))
    assert variant.discount_percent is None


@pytest.mark.django_db
def test_discount_percent_computed_correctly() -> None:
    variant = ProductVariantFactory(price=Decimal("75.00"), compare_at_price=Decimal("100.00"))
    assert variant.discount_percent == 25


@pytest.mark.django_db
def test_is_in_stock_and_is_low_stock() -> None:
    out_of_stock = ProductVariantFactory(stock_quantity=0, low_stock_threshold=5)
    assert out_of_stock.is_in_stock is False
    assert out_of_stock.is_low_stock is False

    low = ProductVariantFactory(stock_quantity=3, low_stock_threshold=5)
    assert low.is_in_stock is True
    assert low.is_low_stock is True

    healthy = ProductVariantFactory(stock_quantity=50, low_stock_threshold=5)
    assert healthy.is_in_stock is True
    assert healthy.is_low_stock is False


@pytest.mark.django_db
def test_with_available_quantity_annotation_matches_stock_quantity() -> None:
    """Stage 2: available_quantity == stock_quantity (Stage 4 changes the
    expression, not the call site, once reservations exist)."""
    variant = ProductVariantFactory(stock_quantity=42)
    annotated = ProductVariant.objects.with_available_quantity().get(pk=variant.pk)
    assert annotated.available_quantity == 42


@pytest.mark.django_db
def test_only_one_default_variant_per_product() -> None:
    product = ProductFactory()  # default variant already is_default=True
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductVariantFactory(product=product, is_default=True)


@pytest.mark.django_db
def test_two_variants_with_identical_attribute_set_raise_integrity_error() -> None:
    """Acceptance gate 4."""
    product = ProductFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")

    v1 = ProductVariantFactory(product=product, sku="V1")
    VariantAttributeValue.objects.create(variant=v1, value=size_50)

    v2 = ProductVariantFactory(product=product, sku="V2")
    with pytest.raises(IntegrityError), transaction.atomic():
        VariantAttributeValue.objects.create(variant=v2, value=size_50)


@pytest.mark.django_db
def test_variants_with_different_attribute_sets_are_both_allowed() -> None:
    product = ProductFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    size_100 = AttributeValueFactory(definition=size, value="100ml")

    v1 = ProductVariantFactory(product=product, sku="V1")
    VariantAttributeValue.objects.create(variant=v1, value=size_50)
    v2 = ProductVariantFactory(product=product, sku="V2")
    VariantAttributeValue.objects.create(variant=v2, value=size_100)

    assert ProductVariant.objects.filter(product=product).count() == 3  # default + v1 + v2


@pytest.mark.django_db
def test_two_variants_with_no_attributes_at_all_are_both_allowed() -> None:
    """The default (blank-signature) variant and a second, also-blank
    variant must coexist — the uniqueness constraint excludes blank
    signatures precisely so a variant can exist for the moment between its
    own creation and its VariantAttributeValue rows being attached."""
    product = ProductFactory()
    ProductVariantFactory(product=product, sku="NO-ATTRS")
    assert ProductVariant.objects.filter(product=product, attribute_signature="").count() == 2


@pytest.mark.django_db
def test_attribute_signature_sorts_numerically_not_lexically() -> None:
    """ids 2 and 10 must join as "2,10" — a lexical sort of the stringified
    ids would produce "10,2"."""
    product = ProductFactory()
    variant = ProductVariantFactory(product=product, sku="SORT-TEST")
    definition = AttributeDefinitionFactory(name="SortAttr")

    value_low_id = AttributeValue.objects.create(pk=2, definition=definition, value="B")
    for skip_pk in range(3, 10):
        AttributeValue.objects.create(pk=skip_pk, definition=definition, value=f"skip{skip_pk}")
    value_high_id = AttributeValue.objects.create(pk=10, definition=definition, value="A")

    # Attach in an order that would expose a naive/lexical sort: high id first.
    VariantAttributeValue.objects.create(variant=variant, value=value_high_id)
    VariantAttributeValue.objects.create(variant=variant, value=value_low_id)

    variant.refresh_from_db()
    assert variant.attribute_signature == "2,10"


@pytest.mark.django_db
def test_removing_a_variant_attribute_value_updates_the_signature() -> None:
    product = ProductFactory()
    variant = ProductVariantFactory(product=product, sku="REMOVE-TEST")
    definition = AttributeDefinitionFactory(name="RemoveAttr")
    value = AttributeValueFactory(definition=definition, value="Only")

    vav = VariantAttributeValue.objects.create(variant=variant, value=value)
    variant.refresh_from_db()
    assert variant.attribute_signature == str(value.pk)

    vav.delete()
    variant.refresh_from_db()
    assert variant.attribute_signature == ""
