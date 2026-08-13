"""orders.state_machine.transition_status — roadmap Stage 10 gates 1, 5, 6.

Built through the real ``orders.services.create_order()`` transaction
(cart -> checkout), not ``OrderFactory`` directly, so every test starts
from an order that actually holds a real ``StockReservation`` the way a
production order would — the same reasoning ``orders/tests/
test_services.py`` already uses for its own fixtures.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from cart.factories import CartFactory, CartItemFactory
from catalog.factories import ProductFactory
from inventory.models import StockReservation
from orders import services
from orders.models import Order, OrderStatusEvent
from orders.state_machine import InvalidStatusTransitionError, transition_status
from orders.status import ALLOWED_TRANSITIONS, Status
from store.models import DeliveryStrategy, StoreSettings


def _flat_rate_delivery(rate: Decimal = Decimal("0.00")) -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FLAT_RATE
    settings_obj.flat_delivery_rate = rate
    settings_obj.save()


def _checkout_input(**overrides: str) -> services.CheckoutInput:
    defaults: dict[str, str] = {
        "name": "Ayesha Khan",
        "phone": "+923001234567",
        "whatsapp_number": "+923001234567",
        "email": "ayesha@example.com",
        "address": "House 1, Street 2",
        "city": "Karachi",
        "postal_code": "75500",
        "instructions": "",
        "notes": "",
    }
    defaults.update(overrides)
    return services.CheckoutInput(**defaults)  # type: ignore[arg-type]


def _pending_order(quantity: int = 2, price: Decimal = Decimal("500.00")) -> Order:
    _flat_rate_delivery()
    product = ProductFactory(default_variant_price=price)
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=quantity)
    return services.create_order(cart=cart, checkout_input=_checkout_input())


@pytest.mark.django_db
def test_gate1_pending_to_confirmed_commits_reservations_and_decrements_stock() -> None:
    order = _pending_order(quantity=3)
    item = order.items.get()
    variant = item.variant
    assert variant is not None
    starting_stock = variant.stock_quantity

    updated = transition_status(order=order, to_status=Status.CONFIRMED, actor=None)

    assert updated.status == Status.CONFIRMED
    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock - 3
    assert not StockReservation.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_gate1_the_full_happy_path_chain_succeeds() -> None:
    order = _pending_order()
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
        Status.OUT_FOR_DELIVERY,
        Status.DELIVERED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)
    assert order.status == Status.DELIVERED


@pytest.mark.django_db
def test_gate1_every_entry_in_the_allowed_transition_map_actually_succeeds() -> None:
    """Every edge the map claims is legal must actually apply without
    raising — walked independently per edge (a fresh order per edge)
    rather than chaining through the whole map in one pass, so an edge
    reachable only via a specific prior state still gets exercised."""
    for from_status, targets in ALLOWED_TRANSITIONS.items():
        for to_status in targets:
            order = _pending_order()
            order.status = from_status
            order.save(update_fields=["status", "updated_at"])
            transition_status(order=order, to_status=to_status, actor=None)  # must not raise


@pytest.mark.django_db
def test_gate1_a_disallowed_transition_raises() -> None:
    order = _pending_order()

    with pytest.raises(InvalidStatusTransitionError):
        transition_status(order=order, to_status=Status.DISPATCHED, actor=None)

    order.refresh_from_db()
    assert order.status == Status.PENDING_CONFIRMATION


@pytest.mark.django_db
def test_a_terminal_status_has_no_outgoing_transitions() -> None:
    order = _pending_order()
    transition_status(order=order, to_status=Status.CANCELLED, actor=None)

    with pytest.raises(InvalidStatusTransitionError):
        transition_status(order=order, to_status=Status.CONFIRMED, actor=None)


@pytest.mark.django_db
def test_pending_to_cancelled_releases_reservations_without_touching_stock() -> None:
    order = _pending_order(quantity=4)
    variant = order.items.get().variant
    assert variant is not None
    starting_stock = variant.stock_quantity

    transition_status(order=order, to_status=Status.CANCELLED, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock
    assert not StockReservation.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_pending_to_expired_releases_reservations_without_touching_stock() -> None:
    order = _pending_order(quantity=2)
    variant = order.items.get().variant
    assert variant is not None
    starting_stock = variant.stock_quantity

    transition_status(order=order, to_status=Status.EXPIRED, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock


@pytest.mark.django_db
def test_gate5_cancel_after_confirm_restores_exactly_the_confirmed_quantity() -> None:
    order = _pending_order(quantity=5)
    variant = order.items.get().variant
    assert variant is not None
    starting_stock = variant.stock_quantity
    transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock - 5

    transition_status(order=order, to_status=Status.CANCELLED, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock


@pytest.mark.django_db
def test_delivered_to_returned_restores_stock() -> None:
    order = _pending_order(quantity=2)
    variant = order.items.get().variant
    assert variant is not None
    starting_stock = variant.stock_quantity
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
        Status.OUT_FOR_DELIVERY,
        Status.DELIVERED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)
    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock - 2

    transition_status(order=order, to_status=Status.RETURNED, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == starting_stock


@pytest.mark.django_db
def test_transition_writes_a_status_event_with_actor_and_note() -> None:
    user_model = get_user_model()
    owner = user_model.objects.create_user(username="owner", password="x")
    order = _pending_order()

    transition_status(
        order=order, to_status=Status.CONFIRMED, actor=owner, note="Called to confirm"
    )

    event = OrderStatusEvent.objects.get(order=order, to_status=Status.CONFIRMED)
    assert event.from_status == Status.PENDING_CONFIRMATION
    assert event.actor == owner
    assert event.note == "Called to confirm"


@pytest.mark.django_db
def test_gate6_timeline_lists_every_transition_in_order_with_actor_and_timestamp() -> None:
    user_model = get_user_model()
    owner = user_model.objects.create_user(username="owner2", password="x")
    order = _pending_order()
    transition_status(order=order, to_status=Status.CONFIRMED, actor=owner)
    transition_status(order=order, to_status=Status.PROCESSING, actor=owner)

    events = list(order.status_events.all())
    assert [e.to_status for e in events] == [
        Status.PENDING_CONFIRMATION,
        Status.CONFIRMED,
        Status.PROCESSING,
    ]
    assert events[0].actor is None  # the creation event — the customer's own checkout
    assert events[0].from_status == ""
    assert events[1].actor == owner
    assert all(e.created_at is not None for e in events)


@pytest.mark.django_db
def test_a_failed_transition_leaves_no_partial_status_event() -> None:
    order = _pending_order()
    with pytest.raises(InvalidStatusTransitionError):
        transition_status(order=order, to_status=Status.DELIVERED, actor=None)

    assert OrderStatusEvent.objects.filter(order=order, to_status=Status.DELIVERED).count() == 0
