from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from cart.factories import CartFactory, CartItemFactory
from catalog.factories import ProductFactory, ProductVariantFactory


@pytest.mark.django_db
def test_deleting_a_variant_sets_the_cart_items_variant_to_null() -> None:
    """The FK is on_delete=SET_NULL, not CASCADE — deleting a variant a
    customer already added must not take their cart item (or cart) down
    with it (roadmap gate 3's "deleted" case). A second variant on the
    product is required here so the deletion itself is legal — a product
    must always have at least one variant (catalog's own invariant,
    unrelated to cart); this test is about what happens to the *cart item*
    when a variant it references is deleted, not about whether that
    deletion is allowed."""
    product = ProductFactory()
    variant = product.variants.get()
    ProductVariantFactory(product=product)
    item = CartItemFactory(variant=variant, quantity=2)

    variant.delete()
    item.refresh_from_db()

    assert item.variant_id is None
    assert item.quantity == 2


@pytest.mark.django_db
def test_quantity_must_be_at_least_one() -> None:
    cart = CartFactory()
    variant = ProductFactory().variants.get()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CartItemFactory(cart=cart, variant=variant, quantity=0)


@pytest.mark.django_db
def test_a_cart_cannot_have_two_items_for_the_same_variant() -> None:
    cart = CartFactory()
    variant = ProductFactory().variants.get()
    CartItemFactory(cart=cart, variant=variant, quantity=1)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CartItemFactory(cart=cart, variant=variant, quantity=1)


@pytest.mark.django_db
def test_cart_and_cart_item_str() -> None:
    cart = CartFactory(session_key="abc123")
    item = CartItemFactory(cart=cart, variant=ProductFactory().variants.get(), quantity=3)

    assert str(cart) == "Cart(abc123)"
    assert str(item) == f"3 x variant#{item.variant_id}"


@pytest.mark.django_db
def test_two_items_with_a_null_variant_in_the_same_cart_do_not_collide() -> None:
    """Postgres treats each NULL as distinct in a unique index — two lines
    that both lost their variant to a deletion are two separate rows, not
    a uniqueness violation."""
    cart = CartFactory()
    first_product = ProductFactory()
    ProductVariantFactory(product=first_product)
    second_product = ProductFactory()
    ProductVariantFactory(product=second_product)
    first = CartItemFactory(cart=cart, variant=first_product.variants.get(is_default=True))
    second = CartItemFactory(cart=cart, variant=second_product.variants.get(is_default=True))

    first.variant.delete()
    second.variant.delete()
    first.refresh_from_db()
    second.refresh_from_db()

    assert first.variant_id is None
    assert second.variant_id is None
