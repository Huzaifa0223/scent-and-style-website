"""cart.services — the only sanctioned way to read or mutate a cart.
Roadmap Stage 7 gates 1-3 live here at the service layer; cart/tests/
test_views.py covers the same gates at the HTTP layer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from cart import services
from cart.factories import CartFactory, CartItemFactory
from cart.models import Cart
from catalog.factories import ProductFactory, ProductVariantFactory


def _request_with_session(rf: RequestFactory):  # type: ignore[no-untyped-def]
    request = rf.get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    return request


def _variant_with_stock(quantity: int):  # type: ignore[no-untyped-def]
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    return variant


@pytest.mark.django_db
def test_get_cart_returns_none_without_creating_anything(rf: RequestFactory) -> None:  # type: ignore[no-untyped-def]
    """Browsing must never create a session or a Cart row for a visitor
    who hasn't added anything — get_cart() is read-only."""
    request = _request_with_session(rf)

    assert services.get_cart(request) is None
    assert Cart.objects.count() == 0


@pytest.mark.django_db
def test_get_or_create_cart_creates_a_session_and_a_cart_row_once(rf: RequestFactory) -> None:  # type: ignore[no-untyped-def]
    request = _request_with_session(rf)

    first = services.get_or_create_cart(request)
    second = services.get_or_create_cart(request)

    assert first.pk == second.pk
    assert Cart.objects.count() == 1


@pytest.mark.django_db
def test_add_item_refuses_beyond_available_quantity_with_the_real_number() -> None:
    """Gate 1."""
    variant = _variant_with_stock(3)
    cart = CartFactory()

    with pytest.raises(services.CartMutationError) as exc_info:
        services.add_item(cart, variant_id=variant.pk, quantity=5)

    assert exc_info.value.available_quantity == 3
    assert cart.items.count() == 0


@pytest.mark.django_db
def test_add_item_twice_accumulates_against_the_same_available_ceiling() -> None:
    """Gate 1 — the check is against the *total* requested (existing +
    new), not just the new quantity in isolation."""
    variant = _variant_with_stock(5)
    cart = CartFactory()

    services.add_item(cart, variant_id=variant.pk, quantity=3)
    with pytest.raises(services.CartMutationError) as exc_info:
        services.add_item(cart, variant_id=variant.pk, quantity=3)

    assert exc_info.value.available_quantity == 5
    assert cart.items.get().quantity == 3


@pytest.mark.django_db
def test_add_item_for_an_existing_variant_increments_the_same_row() -> None:
    variant = _variant_with_stock(10)
    cart = CartFactory()

    services.add_item(cart, variant_id=variant.pk, quantity=2)
    services.add_item(cart, variant_id=variant.pk, quantity=3)

    assert cart.items.count() == 1
    assert cart.items.get().quantity == 5


@pytest.mark.django_db
def test_add_item_for_a_deactivated_variant_refuses_with_zero_available() -> None:
    """Gate 3's "deactivated" case, at the add path."""
    variant = _variant_with_stock(10)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])
    cart = CartFactory()

    with pytest.raises(services.CartMutationError) as exc_info:
        services.add_item(cart, variant_id=variant.pk, quantity=1)

    assert exc_info.value.available_quantity == 0


@pytest.mark.django_db
def test_increment_item_refuses_beyond_available_quantity() -> None:
    variant = _variant_with_stock(2)
    item = CartItemFactory(variant=variant, quantity=2)

    with pytest.raises(services.CartMutationError) as exc_info:
        services.increment_item(item)

    assert exc_info.value.available_quantity == 2
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_increment_item_on_a_deactivated_variant_refuses_without_a_crash() -> None:
    """Gate 3's "deactivated" case, at the increment path."""
    variant = _variant_with_stock(10)
    item = CartItemFactory(variant=variant, quantity=1)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])

    with pytest.raises(services.CartMutationError) as exc_info:
        services.increment_item(item)

    assert exc_info.value.available_quantity == 0


@pytest.mark.django_db
def test_increment_item_on_a_deleted_variant_refuses_without_a_crash() -> None:
    """Gate 3's "deleted" case, at the increment path — item.variant_id is
    None, so this must not even attempt the with_available_quantity()
    lookup."""
    product = ProductFactory()
    variant = product.variants.get()
    ProductVariantFactory(product=product)
    item = CartItemFactory(variant=variant, quantity=1)
    variant.delete()
    item.refresh_from_db()

    with pytest.raises(services.CartMutationError) as exc_info:
        services.increment_item(item)

    assert exc_info.value.available_quantity == 0


@pytest.mark.django_db
def test_decrement_item_below_one_deletes_the_row() -> None:
    variant = _variant_with_stock(10)
    item = CartItemFactory(variant=variant, quantity=1)

    result = services.decrement_item(item)

    assert result is None
    assert not item.__class__.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_decrement_item_is_allowed_even_when_the_variant_is_deactivated() -> None:
    """A customer must always be able to reduce or remove a line that's no
    longer purchasable — only adding more is gated."""
    variant = _variant_with_stock(10)
    item = CartItemFactory(variant=variant, quantity=2)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])

    result = services.decrement_item(item)

    assert result is not None
    assert result.quantity == 1


@pytest.mark.django_db
def test_remove_item_deletes_regardless_of_variant_state() -> None:
    item = CartItemFactory(variant=_variant_with_stock(10))

    services.remove_item(item)

    assert not item.__class__.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_clear_cart_removes_every_item() -> None:
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=_variant_with_stock(5))
    CartItemFactory(cart=cart, variant=_variant_with_stock(5))

    services.clear_cart(cart)

    assert cart.items.count() == 0


@pytest.mark.django_db
def test_cart_lines_flags_a_variant_that_went_out_of_stock_after_adding() -> None:
    """Gate 2 — flagged, not silently dropped."""
    variant = _variant_with_stock(5)
    cart = CartFactory()
    services.add_item(cart, variant_id=variant.pk, quantity=3)
    variant.stock_quantity = 0
    variant.save(update_fields=["stock_quantity", "updated_at"])

    lines = services.cart_lines(cart)

    assert len(lines) == 1
    line = lines[0]
    assert line.item.quantity == 3
    assert line.purchasable_quantity == 0
    assert line.needs_attention is True
    assert line.unavailable_reason == "Out of stock."
    assert line.line_total == Decimal("0.00")


@pytest.mark.django_db
def test_cart_lines_flags_a_partially_reduced_variant() -> None:
    variant = _variant_with_stock(5)
    cart = CartFactory()
    services.add_item(cart, variant_id=variant.pk, quantity=5)
    variant.stock_quantity = 2
    variant.save(update_fields=["stock_quantity", "updated_at"])

    line = services.cart_lines(cart)[0]

    assert line.purchasable_quantity == 2
    assert line.needs_attention is True
    assert "Only 2 left" in line.unavailable_reason
    assert line.line_total == variant.price * 2


@pytest.mark.django_db
def test_cart_lines_handles_a_deactivated_variant_without_a_500() -> None:
    """Gate 3's "deactivated" case, at render time — cart_lines() must not
    raise, and must flag the line as unpurchasable."""
    variant = _variant_with_stock(5)
    cart = CartFactory()
    services.add_item(cart, variant_id=variant.pk, quantity=2)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])

    line = services.cart_lines(cart)[0]

    assert line.variant is not None
    assert line.purchasable_quantity == 0
    assert line.needs_attention is True
    assert line.unavailable_reason == "This item is no longer available."


@pytest.mark.django_db
def test_cart_lines_handles_a_deleted_variant_without_a_500() -> None:
    """Gate 3's "deleted" case, at render time."""
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])
    ProductVariantFactory(product=product)
    cart = CartFactory()
    services.add_item(cart, variant_id=variant.pk, quantity=2)
    variant.delete()

    line = services.cart_lines(cart)[0]

    assert line.variant is None
    assert line.purchasable_quantity == 0
    assert line.needs_attention is True
    assert line.unavailable_reason == "This item is no longer available."
    assert line.line_total == Decimal("0.00")
    assert line.item.quantity == 2


@pytest.mark.django_db
def test_cart_lines_is_fully_available_when_nothing_changed() -> None:
    variant = _variant_with_stock(10)
    cart = CartFactory()
    services.add_item(cart, variant_id=variant.pk, quantity=2)

    line = services.cart_lines(cart)[0]

    assert line.needs_attention is False
    assert line.unavailable_reason == ""
    assert line.line_total == variant.price * 2


@pytest.mark.django_db
def test_cart_subtotal_sums_only_the_purchasable_portion_of_each_line() -> None:
    cart = CartFactory()
    available = _variant_with_stock(10)
    services.add_item(cart, variant_id=available.pk, quantity=2)
    out_of_stock = _variant_with_stock(5)
    services.add_item(cart, variant_id=out_of_stock.pk, quantity=1)
    out_of_stock.stock_quantity = 0
    out_of_stock.save(update_fields=["stock_quantity", "updated_at"])

    lines = services.cart_lines(cart)
    subtotal = services.cart_subtotal(lines)

    assert subtotal == available.price * 2


@pytest.mark.django_db
def test_cart_lines_query_count_stays_flat_as_item_count_grows_from_1_to_5() -> None:
    """cart_lines()'s own docstring claims two queries regardless of item
    count. Asserted directly here, not just observed indirectly through
    the view-level test in test_views.py, because this function also runs
    on every storefront page via the globally-registered context
    processor — a regression here costs every page on the site, not just
    the cart drawer itself."""
    cart = CartFactory()
    services.add_item(cart, variant_id=_variant_with_stock(5).pk, quantity=1)
    with CaptureQueriesContext(connection) as captured_at_1:
        services.cart_lines(cart)
    queries_at_1 = len(captured_at_1)

    for _ in range(4):
        services.add_item(cart, variant_id=_variant_with_stock(5).pk, quantity=1)
    assert cart.items.count() == 5
    with CaptureQueriesContext(connection) as captured_at_5:
        services.cart_lines(cart)
    queries_at_5 = len(captured_at_5)

    assert queries_at_5 == queries_at_1, (
        f"query count grew with item count: {queries_at_1} at 1, {queries_at_5} at 5 — "
        "likely an N+1"
    )
