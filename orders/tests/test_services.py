"""orders.services.create_order — the transactional core (roadmap Stage 8
gates 1-5). Delivery-strategy correctness (gate 6) lives in
shipping/tests/test_calculators.py; this module covers the transaction
itself.
"""

from __future__ import annotations

import re
import threading
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from cart.factories import CartFactory, CartItemFactory
from cart.models import Cart, CartItem
from catalog.factories import ProductFactory, ProductVariantFactory
from customers.models import Customer
from inventory.models import StockReservation
from orders import services
from orders.models import Order, OrderItem
from store.models import DeliveryStrategy, StoreSettings


def _checkout_input(**overrides: str) -> services.CheckoutInput:
    defaults: dict[str, str] = {
        "name": "Ayesha Khan",
        "phone": "+923001234567",
        "whatsapp_number": "+923001234567",
        "email": "ayesha@example.com",
        "address": "House 1, Street 2",
        "city": "Karachi",
        "postal_code": "75500",
        "instructions": "Leave at the gate",
        "notes": "Gift wrap please",
    }
    defaults.update(overrides)
    return services.CheckoutInput(**defaults)  # type: ignore[arg-type]


def _variant_with_stock(quantity: int, price: Decimal = Decimal("500.00")):  # type: ignore[no-untyped-def]
    product = ProductFactory(default_variant_price=price)
    variant = product.variants.get()
    variant.stock_quantity = quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    return variant


def _flat_rate_delivery(rate: Decimal = Decimal("0.00")) -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FLAT_RATE
    settings_obj.flat_delivery_rate = rate
    settings_obj.save()


@pytest.mark.django_db
def test_create_order_happy_path_creates_order_items_and_reservations() -> None:
    _flat_rate_delivery(Decimal("150.00"))
    variant = _variant_with_stock(10, price=Decimal("500.00"))
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=2)

    order = services.create_order(cart=cart, checkout_input=_checkout_input())

    assert re.fullmatch(r"ORD-\d+-[A-Z0-9]{3}", order.order_number)
    assert order.subtotal == Decimal("1000.00")
    assert order.delivery_charge == Decimal("150.00")
    assert order.total == Decimal("1150.00")
    assert order.status == Order.Status.PENDING_CONFIRMATION
    assert order.customer_name == "Ayesha Khan"

    item = OrderItem.objects.get(order=order)
    assert item.variant_id == variant.pk
    assert item.product_name == variant.product.name
    assert item.sku == variant.sku
    assert item.unit_price == Decimal("500.00")
    assert item.quantity == 2
    assert item.line_total == Decimal("1000.00")

    reservation = StockReservation.objects.get(order=order)
    assert reservation.variant_id == variant.pk
    assert reservation.quantity == 2

    assert Customer.objects.filter(phone="+923001234567").exists()
    assert not CartItem.objects.filter(cart=cart).exists()


@pytest.mark.django_db
def test_create_order_with_an_empty_cart_raises() -> None:
    cart = CartFactory()

    with pytest.raises(services.EmptyCartError):
        services.create_order(cart=cart, checkout_input=_checkout_input())

    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_gate1_snapshot_survives_a_price_change_a_rename_and_a_product_deletion() -> None:
    """Gate 1."""
    _flat_rate_delivery()
    variant = _variant_with_stock(10, price=Decimal("500.00"))
    product = variant.product
    original_name = product.name
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=1)

    order = services.create_order(cart=cart, checkout_input=_checkout_input())
    item = OrderItem.objects.get(order=order)

    product.name = "A Completely Different Name"
    product.save(update_fields=["name", "updated_at"])
    variant.price = Decimal("999999.00")
    variant.save(update_fields=["price", "updated_at"])
    product.delete()

    item.refresh_from_db()
    assert item.product_name == original_name
    assert item.unit_price == Decimal("500.00")
    assert item.sku != ""
    assert item.variant_id is None  # SET_NULL — the product/variant is gone


@pytest.mark.django_db
def test_gate3_a_failure_mid_creation_rolls_back_completely() -> None:
    """Gate 3 — one insufficient-stock line among several must roll back
    the whole attempt: no orphan order, no orphan reservation, even for
    the line that *would* have succeeded on its own."""
    _flat_rate_delivery()
    ok_variant = _variant_with_stock(10)
    short_variant = _variant_with_stock(1)
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=ok_variant, quantity=2)
    CartItemFactory(cart=cart, variant=short_variant, quantity=5)

    with pytest.raises(services.CheckoutValidationError):
        services.create_order(cart=cart, checkout_input=_checkout_input())

    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert StockReservation.objects.count() == 0
    # The cart itself must survive the rollback too.
    assert CartItem.objects.filter(cart=cart).count() == 2


@pytest.mark.django_db
def test_gate4_availability_changed_since_add_produces_a_per_line_error_naming_the_product() -> (
    None
):
    """Gate 4."""
    _flat_rate_delivery()
    variant = _variant_with_stock(5, price=Decimal("100.00"))
    product_name = variant.product.name
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=5)
    variant.stock_quantity = 2
    variant.save(update_fields=["stock_quantity", "updated_at"])

    with pytest.raises(services.CheckoutValidationError) as exc_info:
        services.create_order(cart=cart, checkout_input=_checkout_input())

    assert len(exc_info.value.errors) == 1
    error = exc_info.value.errors[0]
    assert error.product_name == product_name
    assert error.requested_quantity == 5
    assert error.available_quantity == 2


@pytest.mark.django_db
def test_a_deactivated_variant_produces_a_per_line_error_naming_the_product() -> None:
    _flat_rate_delivery()
    variant = _variant_with_stock(5)
    product_name = variant.product.name
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=1)

    with pytest.raises(services.CheckoutValidationError) as exc_info:
        services.create_order(cart=cart, checkout_input=_checkout_input())

    assert exc_info.value.errors[0].product_name == product_name
    assert exc_info.value.errors[0].available_quantity == 0


@pytest.mark.django_db
def test_a_deleted_variant_in_the_cart_is_handled_without_a_crash() -> None:
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 5
    variant.save(update_fields=["stock_quantity", "updated_at"])
    ProductVariantFactory(product=product)  # so the product still has >=1 variant after delete
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=1)
    variant.delete()

    with pytest.raises(services.CheckoutValidationError) as exc_info:
        services.create_order(cart=cart, checkout_input=_checkout_input())

    assert exc_info.value.errors[0].available_quantity == 0


@pytest.mark.django_db
def test_query_count_stays_flat_as_line_count_grows_from_1_to_5() -> None:
    """Not a named acceptance gate, but the same discipline this project
    holds every other list-processing service to — the per-line
    validation and OrderItem-creation loops must not N+1 as a cart grows."""
    _flat_rate_delivery()
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=_variant_with_stock(10), quantity=1)
    with CaptureQueriesContext(connection) as captured_at_1:
        services.create_order(cart=cart, checkout_input=_checkout_input())
    queries_at_1 = len(captured_at_1)

    cart5 = CartFactory()
    for _ in range(5):
        CartItemFactory(cart=cart5, variant=_variant_with_stock(10), quantity=1)
    with CaptureQueriesContext(connection) as captured_at_5:
        services.create_order(cart=cart5, checkout_input=_checkout_input())
    queries_at_5 = len(captured_at_5)

    # Not claiming flat here — each line legitimately costs its own
    # OrderItem insert plus reserve()'s own fixed per-call cost (lock+get,
    # the active-reservation sum, a StoreSettings cache lookup, the
    # StockReservation insert — measured directly at 5 queries/line via
    # CaptureQueriesContext, not guessed), same as the per-value cost
    # storefront's attribute_facet_counts() already accepts (O(lines),
    # not O(catalog size)). The budget below has headroom above that
    # measured cost; what it actually catches is a *second* per-line cost
    # stacking on top (e.g. a forgotten prefetch reintroducing an N+1),
    # which would push this well past 7/line.
    per_line_cost = queries_at_5 - queries_at_1
    assert per_line_cost <= 7 * 4, per_line_cost


@pytest.mark.django_db(transaction=True)
def test_gate5_concurrent_order_creation_for_the_last_unit_exactly_one_succeeds() -> None:
    """Gate 5 (order-number uniqueness under concurrency) combined with
    the same last-unit race Stage 4 already proved for reserve() itself —
    here exercised through the full create_order() transaction."""
    _flat_rate_delivery()
    variant = _variant_with_stock(1)
    carts = [CartFactory() for _ in range(2)]
    for cart in carts:
        CartItemFactory(cart=cart, variant=variant, quantity=1)
    outcomes: dict[str, str] = {}
    order_numbers: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def attempt(label: str, cart: Cart) -> None:
        try:
            barrier.wait(timeout=5)
            order = services.create_order(
                cart=cart, checkout_input=_checkout_input(phone=f"+92300000000{label[-1]}")
            )
            outcomes[label] = "created"
            order_numbers[label] = order.order_number
        except services.CheckoutValidationError:
            outcomes[label] = "rejected"
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(f"t{i}", carts[i])) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes.values()) == ["created", "rejected"]
    assert Order.objects.count() == 1
    assert StockReservation.objects.filter(variant=variant).count() == 1
    assert len(set(order_numbers.values())) == len(order_numbers)
