"""HTTP-level tests for cart/views.py — roadmap Stage 7's five acceptance
gates, exercised end to end through the Django test client rather than the
service layer directly (cart/tests/test_services.py already covers that).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from cart.factories import CartFactory, CartItemFactory
from cart.models import Cart
from catalog.factories import ProductFactory, ProductVariantFactory

ADD_URL = "/cart/add/"


def _variant_with_stock(quantity: int):  # type: ignore[no-untyped-def]
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    return variant


@pytest.mark.django_db
def test_add_refuses_beyond_available_quantity_with_the_real_number(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 1."""
    variant = _variant_with_stock(2)

    response = client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 5})

    assert response.status_code == 200
    assert b"Only 2 left in stock." in response.content
    cart = Cart.objects.get()
    assert cart.items.count() == 0


@pytest.mark.django_db
def test_add_within_available_quantity_succeeds_and_updates_the_badge(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)

    response = client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 2})

    assert response.status_code == 200
    assert b'id="cart-badge-count"' in response.content
    assert b">2<" in response.content
    cart = Cart.objects.get()
    assert cart.items.get().quantity == 2


@pytest.mark.django_db
def test_add_for_a_deactivated_variant_is_refused_without_a_500(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 3's "deactivated" case, at the add path."""
    variant = _variant_with_stock(5)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])

    response = client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})

    assert response.status_code == 200
    assert b"no longer available" in response.content


@pytest.mark.django_db
def test_a_cart_item_that_goes_out_of_stock_after_add_is_flagged_not_dropped(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 2."""
    variant = _variant_with_stock(3)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 3})
    variant.stock_quantity = 0
    variant.save(update_fields=["stock_quantity", "updated_at"])

    # Any subsequent mutation re-renders the drawer from current state —
    # increment the (now unrelated) fact that a second, unaffected add
    # still shows the first line still present and flagged.
    other = _variant_with_stock(5)
    response = client.post(ADD_URL, {"variant_id": other.pk, "quantity": 1})

    assert response.status_code == 200
    assert b"Out of stock." in response.content
    cart = Cart.objects.get()
    assert cart.items.filter(variant=variant).exists()


@pytest.mark.django_db
def test_a_variant_deactivated_after_being_added_is_handled_without_a_500(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 3's "deactivated" case, at render time."""
    variant = _variant_with_stock(3)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])

    response = client.post(ADD_URL, {"variant_id": _variant_with_stock(5).pk, "quantity": 1})

    assert response.status_code == 200
    assert b"no longer available" in response.content


@pytest.mark.django_db
def test_a_variant_deleted_after_being_added_is_handled_without_a_500(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 3's "deleted" case, at render time — the named example in the
    roadmap gate is deactivation, but a deleted variant is the harder
    version of the same failure mode (a NULL FK, not just a flag)."""
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 3
    variant.save(update_fields=["stock_quantity", "updated_at"])
    ProductVariantFactory(product=product)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})
    variant.delete()

    response = client.post(ADD_URL, {"variant_id": _variant_with_stock(5).pk, "quantity": 1})

    assert response.status_code == 200
    assert b"Item unavailable" in response.content


@pytest.mark.django_db
def test_increment_decrement_remove_clear_never_500_and_never_redirect(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 4 — every mutation responds with a fragment (200), never a
    redirect (which would force a full navigation)."""
    variant = _variant_with_stock(10)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})
    item = Cart.objects.get().items.get()

    increment = client.post(f"/cart/items/{item.pk}/increment/")
    decrement = client.post(f"/cart/items/{item.pk}/decrement/")
    remove_response = client.post(f"/cart/items/{item.pk}/remove/")
    clear_response = client.post("/cart/clear/")

    for response in (increment, decrement, remove_response, clear_response):
        assert response.status_code == 200
        assert response.get("Location") is None


@pytest.mark.django_db
def test_decrementing_the_last_unit_removes_the_line(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(10)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})
    item = Cart.objects.get().items.get()

    response = client.post(f"/cart/items/{item.pk}/decrement/")

    assert response.status_code == 200
    assert b"Your cart is empty." in response.content
    assert not Cart.objects.get().items.exists()


@pytest.mark.django_db
def test_mutating_an_item_belonging_to_a_different_session_is_refused() -> None:
    other_cart = CartFactory()
    other_item = CartItemFactory(cart=other_cart, variant=_variant_with_stock(10))
    client = Client()
    client.post(ADD_URL, {"variant_id": _variant_with_stock(5).pk, "quantity": 1})

    response = client.post(f"/cart/items/{other_item.pk}/increment/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_incrementing_without_ever_having_added_anything_404s() -> None:
    client = Client()

    response = client.post("/cart/items/1/increment/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_get_is_not_allowed_on_any_mutation_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})
    item = Cart.objects.get().items.get()

    assert client.get(ADD_URL).status_code == 405
    assert client.get(f"/cart/items/{item.pk}/increment/").status_code == 405
    assert client.get(f"/cart/items/{item.pk}/decrement/").status_code == 405
    assert client.get(f"/cart/items/{item.pk}/remove/").status_code == 405
    assert client.get("/cart/clear/").status_code == 405


@pytest.mark.django_db
def test_csrf_is_enforced_on_the_add_endpoint() -> None:
    client = Client(enforce_csrf_checks=True)
    variant = _variant_with_stock(5)

    response = client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 1})

    assert response.status_code == 403


@pytest.mark.django_db
def test_cart_widget_renders_on_a_storefront_page_with_no_cart_yet(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/")

    assert response.status_code == 200
    assert b'id="cart-widget"' in response.content
    assert Cart.objects.count() == 0


@pytest.mark.django_db
def test_query_count_stays_flat_as_item_count_grows_from_2_to_20(client) -> None:  # type: ignore[no-untyped-def]
    """Same discipline as every other list-rendering view in this project
    (storefront's own gate 5), applied here even though Stage 7's own gate
    list doesn't name it explicitly — the drawer renders every line item
    in a loop, exactly the shape that N+1s."""
    client.get("/")  # warm up StoreSettings.load(), session/cache tables

    for _ in range(2):
        client.post(ADD_URL, {"variant_id": _variant_with_stock(5).pk, "quantity": 1})
    with CaptureQueriesContext(connection) as captured_at_2:
        response = client.get("/")
    assert response.status_code == 200
    queries_at_2 = len(captured_at_2)

    for _ in range(18):
        client.post(ADD_URL, {"variant_id": _variant_with_stock(5).pk, "quantity": 1})
    assert Cart.objects.get().items.count() == 20
    with CaptureQueriesContext(connection) as captured_at_20:
        response = client.get("/")
    assert response.status_code == 200
    queries_at_20 = len(captured_at_20)

    assert queries_at_20 == queries_at_2, (
        f"query count grew with item count: {queries_at_2} at 2, {queries_at_20} at 20 — "
        "likely an N+1"
    )


@pytest.mark.django_db
def test_add_with_a_non_numeric_variant_id_is_refused_without_a_500(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(ADD_URL, {"variant_id": "not-a-number", "quantity": 1})

    assert response.status_code == 200
    # {{ error }} is auto-escaped (no |safe) — the apostrophe renders as &#x27;.
    assert b"Couldn&#x27;t add that item." in response.content


@pytest.mark.django_db
def test_add_with_a_missing_quantity_defaults_to_one(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)

    response = client.post(ADD_URL, {"variant_id": variant.pk})

    assert response.status_code == 200
    cart = Cart.objects.get()
    assert cart.items.get().quantity == 1


@pytest.mark.django_db
def test_increment_beyond_available_quantity_is_refused_with_the_real_number(client) -> None:  # type: ignore[no-untyped-def]
    """Gate 1, at the increment endpoint specifically."""
    variant = _variant_with_stock(2)
    client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 2})
    item = Cart.objects.get().items.get()

    response = client.post(f"/cart/items/{item.pk}/increment/")

    assert response.status_code == 200
    assert b"Only 2 left in stock." in response.content
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_subtotal_and_delivery_placeholder_render(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    variant.price = Decimal("25.00")
    variant.save(update_fields=["price", "updated_at"])

    response = client.post(ADD_URL, {"variant_id": variant.pk, "quantity": 2})

    assert response.status_code == 200
    assert b"Calculated at checkout" in response.content
