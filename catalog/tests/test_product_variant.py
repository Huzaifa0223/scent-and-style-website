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
def test_is_in_stock_and_is_low_stock_annotations_with_no_reservations() -> None:
    """is_in_stock and is_low_stock only exist as queryset annotations
    (Stage 4) — never Python properties, since a property here would be
    exactly the N+1 CLAUDE.md's Traps section warns against. With no
    StockReservation rows at all, available_quantity == stock_quantity, so
    this is also what proves the Coalesce(..., Value(0)) branch works: a
    LEFT JOIN that matches nothing must read as 0, not NULL propagating
    into "false for everything". inventory/tests/ covers the case where a
    reservation actually reduces availability below stock_quantity."""
    out_of_stock = ProductVariantFactory(stock_quantity=0, low_stock_threshold=5)
    low = ProductVariantFactory(stock_quantity=3, low_stock_threshold=5)
    healthy = ProductVariantFactory(stock_quantity=50, low_stock_threshold=5)

    annotated = {
        variant.pk: variant
        for variant in ProductVariant.objects.with_available_quantity().filter(
            pk__in=[out_of_stock.pk, low.pk, healthy.pk]
        )
    }

    assert annotated[out_of_stock.pk].is_in_stock is False
    assert annotated[out_of_stock.pk].is_low_stock is False
    assert annotated[low.pk].is_in_stock is True
    assert annotated[low.pk].is_low_stock is True
    assert annotated[healthy.pk].is_in_stock is True
    assert annotated[healthy.pk].is_low_stock is False


@pytest.mark.django_db
def test_with_available_quantity_annotation_matches_stock_quantity_with_no_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=42)
    annotated = ProductVariant.objects.with_available_quantity().get(pk=variant.pk)
    assert annotated.available_quantity == 42


@pytest.mark.django_db(transaction=True)
def test_only_one_default_variant_per_product() -> None:
    """at-most-one-default is a deferred constraint trigger (migration
    0003), not a plain unique index — needs a real commit to observe."""
    product = ProductFactory()  # default variant already is_default=True
    with pytest.raises(IntegrityError):
        ProductVariantFactory(product=product, is_default=True)


@pytest.mark.django_db(transaction=True)
def test_default_variant_swap_succeeds_even_when_set_before_unset() -> None:
    """The whole reason this invariant is a deferred trigger rather than an
    immediate unique index: Stage 3's variant formset can't guarantee
    "unset the old default before setting the new one" statement order.
    Setting the new default first — which would fail immediately against a
    non-deferred constraint, since two rows are briefly both True — must
    still succeed here because the check only runs at COMMIT."""
    product = ProductFactory()
    old_default = product.variants.get(is_default=True)
    new_default = ProductVariantFactory(product=product, is_default=False)

    with transaction.atomic():
        new_default.is_default = True
        new_default.save(update_fields=["is_default", "updated_at"])
        old_default.is_default = False
        old_default.save(update_fields=["is_default", "updated_at"])

    old_default.refresh_from_db()
    new_default.refresh_from_db()
    assert old_default.is_default is False
    assert new_default.is_default is True


@pytest.mark.django_db(transaction=True)
def test_two_defaults_left_uncorrected_still_fail_at_commit() -> None:
    """Deferred doesn't mean unenforced — an invalid final state still
    raises, just at COMMIT instead of at the offending statement."""
    product = ProductFactory()
    new_default = ProductVariantFactory(product=product, is_default=False)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            new_default.is_default = True
            new_default.save(update_fields=["is_default", "updated_at"])


@pytest.mark.django_db
def test_deleting_the_default_variant_promotes_the_next_by_position() -> None:
    """migration 0003's trigger only covers INSERT/UPDATE — a DELETE of the
    default row needs its own promotion, mirroring
    ProductImage.delete()'s primary-image promotion."""
    product = ProductFactory()  # default variant already is_default=True
    second = ProductVariantFactory(product=product, sku="SECOND", position=1)
    default = product.variants.get(is_default=True)

    default.delete()

    second.refresh_from_db()
    assert second.is_default is True


@pytest.mark.django_db
def test_deleting_old_default_after_explicit_reassignment_leaves_the_new_default_alone() -> None:
    """Proves the guard in ProductVariant.delete() ("promote next by
    position" only fires if no other variant already holds
    is_default=True). third has a lower position than new_default, so
    without the guard, deleting old_default would unconditionally promote
    third — leaving two rows with is_default=True even though the caller
    had already made an explicit, different choice."""
    product = ProductFactory()  # default variant already is_default=True
    old_default = product.variants.get(is_default=True)
    new_default = ProductVariantFactory(product=product, sku="NEW-DEFAULT", position=5)
    third = ProductVariantFactory(product=product, sku="THIRD", position=1)

    new_default.is_default = True
    new_default.save(update_fields=["is_default", "updated_at"])
    old_default.delete()

    assert product.variants.filter(is_default=True).count() == 1
    new_default.refresh_from_db()
    third.refresh_from_db()
    assert new_default.is_default is True
    assert third.is_default is False


@pytest.mark.django_db(transaction=True)
def test_two_variants_with_identical_attribute_set_raise_integrity_error() -> None:
    """Acceptance gate 4. migration 0004 made this constraint a deferred
    trigger — checked at COMMIT, not after the offending statement — so
    this needs a real commit to observe, like the default-variant
    constraint tests above."""
    product = ProductFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")

    v1 = ProductVariantFactory(product=product, sku="V1")
    VariantAttributeValue.objects.create(variant=v1, value=size_50)

    v2 = ProductVariantFactory(product=product, sku="V2")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
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


@pytest.mark.django_db(transaction=True)
def test_swapping_attribute_sets_between_two_variants_succeeds() -> None:
    """The whole reason attribute_signature uniqueness is a deferred
    constraint trigger (migration 0004), not a plain partial unique index:
    the portal formset's own save order (v1 first, v2 second) makes v1's
    saved signature briefly equal v2's still-unchanged one. That must not
    raise, and the immediate version of this constraint would have."""
    product = ProductFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    size_100 = AttributeValueFactory(definition=size, value="100ml")

    v1 = ProductVariantFactory(product=product, sku="V1")
    VariantAttributeValue.objects.create(variant=v1, value=size_50)
    v2 = ProductVariantFactory(product=product, sku="V2")
    VariantAttributeValue.objects.create(variant=v2, value=size_100)

    with transaction.atomic():
        VariantAttributeValue.objects.get(variant=v1, value=size_50).delete()
        VariantAttributeValue.objects.create(variant=v1, value=size_100)
        VariantAttributeValue.objects.get(variant=v2, value=size_100).delete()
        VariantAttributeValue.objects.create(variant=v2, value=size_50)

    v1.refresh_from_db()
    v2.refresh_from_db()
    assert v1.attribute_signature == str(size_100.pk)
    assert v2.attribute_signature == str(size_50.pk)


@pytest.mark.django_db(transaction=True)
def test_deleting_a_variant_and_reassigning_its_attributes_to_a_survivor_succeeds() -> None:
    """Same deferred-trigger reasoning, for the other shape the formset
    must support: deleting v1 while giving its attribute set to a
    previously-blank survivor, saved before the delete (the formset's
    survivors-then-deletes order) — v1 and survivor briefly share the same
    signature until v1's row is gone."""
    product = ProductFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")

    v1 = ProductVariantFactory(product=product, sku="V1")
    VariantAttributeValue.objects.create(variant=v1, value=size_50)
    survivor = ProductVariantFactory(product=product, sku="SURVIVOR")

    with transaction.atomic():
        VariantAttributeValue.objects.create(variant=survivor, value=size_50)
        v1.delete()

    survivor.refresh_from_db()
    assert survivor.attribute_signature == str(size_50.pk)
    assert ProductVariant.objects.filter(pk=v1.pk).exists() is False


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
