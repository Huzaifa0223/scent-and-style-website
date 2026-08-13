"""orders.editing — line quantity/add/remove/price-override actions
(roadmap Stage 10 gates 2-4, requirements §23's order-editing rule).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from cart.factories import CartFactory, CartItemFactory
from catalog.factories import ProductFactory, ProductVariantFactory
from inventory.models import StockReservation
from inventory.services import InsufficientStockError
from orders import editing, services
from orders.models import Order, OrderEditEvent
from orders.state_machine import transition_status
from orders.status import Status
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


def _pending_order(quantity: int = 2, price: Decimal = Decimal("500.00"), stock: int = 10) -> Order:
    _flat_rate_delivery()
    product = ProductFactory(default_variant_price=price)
    variant = product.variants.get()
    variant.stock_quantity = stock
    variant.save(update_fields=["stock_quantity", "updated_at"])
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=quantity)
    return services.create_order(cart=cart, checkout_input=_checkout_input())


@pytest.mark.django_db
def test_gate2_a_quantity_increase_while_pending_reserves_the_delta() -> None:
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()
    variant = item.variant
    assert variant is not None

    editing.change_line_quantity(order=order, item=item, new_quantity=5, actor=None)

    item.refresh_from_db()
    assert item.quantity == 5
    assert item.line_total == item.unit_price * 5
    total_reserved = StockReservation.objects.filter(order=order, variant=variant).count()
    assert total_reserved >= 1
    reserved_quantity = sum(
        StockReservation.objects.filter(order=order, variant=variant).values_list(
            "quantity", flat=True
        )
    )
    assert reserved_quantity == 5
    variant.refresh_from_db()
    assert variant.stock_quantity == 10  # still just reserved, not decremented


@pytest.mark.django_db
def test_gate2_a_quantity_decrease_while_pending_releases_the_delta() -> None:
    order = _pending_order(quantity=5, stock=10)
    item = order.items.get()
    variant = item.variant
    assert variant is not None

    editing.change_line_quantity(order=order, item=item, new_quantity=2, actor=None)

    item.refresh_from_db()
    assert item.quantity == 2
    reserved_quantity = sum(
        StockReservation.objects.filter(order=order, variant=variant).values_list(
            "quantity", flat=True
        )
    )
    assert reserved_quantity == 2


@pytest.mark.django_db
def test_quantity_increase_while_pending_raises_when_insufficient_stock() -> None:
    order = _pending_order(quantity=2, stock=3)
    item = order.items.get()

    with pytest.raises(InsufficientStockError):
        editing.change_line_quantity(order=order, item=item, new_quantity=10, actor=None)

    item.refresh_from_db()
    assert item.quantity == 2  # unchanged


@pytest.mark.django_db
def test_quantity_increase_while_confirmed_consumes_the_delta_directly() -> None:
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()
    variant = item.variant
    assert variant is not None
    transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    variant.refresh_from_db()
    assert variant.stock_quantity == 8  # 10 - 2 committed

    editing.change_line_quantity(order=order, item=item, new_quantity=5, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == 5  # 8 - 3 more consumed directly
    assert StockReservation.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_quantity_decrease_while_confirmed_restores_the_delta_directly() -> None:
    order = _pending_order(quantity=5, stock=10)
    item = order.items.get()
    variant = item.variant
    assert variant is not None
    transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    variant.refresh_from_db()
    assert variant.stock_quantity == 5  # 10 - 5 committed

    editing.change_line_quantity(order=order, item=item, new_quantity=2, actor=None)

    variant.refresh_from_db()
    assert variant.stock_quantity == 8  # 5 + 3 restored


@pytest.mark.django_db
def test_change_line_quantity_to_the_same_value_is_a_noop_and_writes_no_event() -> None:
    order = _pending_order(quantity=3, stock=10)
    item = order.items.get()

    result = editing.change_line_quantity(order=order, item=item, new_quantity=3, actor=None)

    assert result is None
    assert OrderEditEvent.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_gate3_a_price_override_changes_the_total_and_writes_an_audit_row_with_both_values() -> (
    None
):
    order = _pending_order(quantity=2, price=Decimal("500.00"), stock=10)
    item = order.items.get()
    original_total = order.total

    event = editing.override_line_price(
        order=order, item=item, new_unit_price=Decimal("400.00"), actor=None
    )

    item.refresh_from_db()
    order.refresh_from_db()
    assert item.unit_price == Decimal("400.00")
    assert item.line_total == Decimal("800.00")
    assert order.subtotal == Decimal("800.00")
    assert order.total != original_total
    assert event.edit_type == OrderEditEvent.EditType.PRICE_OVERRIDDEN
    event.refresh_from_db()  # prove the JSONField round-trip, not just the in-memory dict
    assert event.before == {"unit_price": "500.00", "line_total": "1000.00"}
    assert event.after == {"unit_price": "400.00", "line_total": "800.00"}


@pytest.mark.django_db
def test_gate4_editing_a_dispatched_order_is_refused() -> None:
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)
    item.refresh_from_db()

    with pytest.raises(editing.OrderNotEditableError):
        editing.change_line_quantity(order=order, item=item, new_quantity=5, actor=None)
    with pytest.raises(editing.OrderNotEditableError):
        editing.override_line_price(
            order=order, item=item, new_unit_price=Decimal("1.00"), actor=None
        )
    with pytest.raises(editing.OrderNotEditableError):
        editing.remove_line(order=order, item=item, actor=None)

    item.refresh_from_db()
    assert item.quantity == 2  # untouched


@pytest.mark.django_db
def test_editing_while_processing_is_refused_per_the_literal_two_status_whitelist() -> None:
    """requirements §23's operative sentence names exactly Pending
    Confirmation and Confirmed — Processing isn't included even though
    it comes before Dispatched (orders/status.py's own module docstring
    records this reading; see specs/state.md's Open questions)."""
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()
    order = transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    order = transition_status(order=order, to_status=Status.PROCESSING, actor=None)
    item.refresh_from_db()

    with pytest.raises(editing.OrderNotEditableError):
        editing.change_line_quantity(order=order, item=item, new_quantity=5, actor=None)


@pytest.mark.django_db
def test_add_line_reserves_the_new_variant_while_pending() -> None:
    order = _pending_order(quantity=1, stock=10)
    new_variant = ProductVariantFactory(stock_quantity=10)

    event = editing.add_line(order=order, variant=new_variant, quantity=3, actor=None)

    assert order.items.filter(variant=new_variant, quantity=3).exists()
    assert StockReservation.objects.filter(order=order, variant=new_variant, quantity=3).exists()
    assert event.edit_type == OrderEditEvent.EditType.LINE_ADDED
    assert event.before is None
    order.refresh_from_db()
    assert order.subtotal == sum((i.line_total for i in order.items.all()), Decimal("0.00"))


@pytest.mark.django_db
def test_add_line_rejects_a_duplicate_variant() -> None:
    order = _pending_order(quantity=1, stock=10)
    existing_variant = order.items.get().variant
    assert existing_variant is not None

    with pytest.raises(editing.LineEditError):
        editing.add_line(order=order, variant=existing_variant, quantity=1, actor=None)


@pytest.mark.django_db
def test_remove_line_releases_the_reservation_and_deletes_the_item() -> None:
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    editing.add_line(order=order, variant=extra_variant, quantity=2, actor=None)
    item_to_remove = order.items.get(variant=extra_variant)

    event = editing.remove_line(order=order, item=item_to_remove, actor=None)

    assert not order.items.filter(pk=item_to_remove.pk).exists()
    assert not StockReservation.objects.filter(order=order, variant=extra_variant).exists()
    assert event.edit_type == OrderEditEvent.EditType.LINE_REMOVED
    assert event.after is None


@pytest.mark.django_db
def test_remove_line_refuses_to_remove_the_last_remaining_line() -> None:
    order = _pending_order(quantity=1, stock=10)
    item = order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.remove_line(order=order, item=item, actor=None)

    assert order.items.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_change_line_quantity_rejects_zero_or_negative() -> None:
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.change_line_quantity(order=order, item=item, new_quantity=0, actor=None)


@pytest.mark.django_db
def test_change_line_quantity_rejects_a_line_from_another_order() -> None:
    order = _pending_order(quantity=2, stock=10)
    other_order = _pending_order(quantity=1, stock=10)
    foreign_item = other_order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.change_line_quantity(order=order, item=foreign_item, new_quantity=3, actor=None)


@pytest.mark.django_db
def test_change_line_quantity_refuses_a_line_whose_variant_was_deleted() -> None:
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    editing.add_line(order=order, variant=extra_variant, quantity=1, actor=None)
    item = order.items.get(variant=extra_variant)
    extra_variant.delete()
    item.refresh_from_db()
    assert item.variant_id is None

    with pytest.raises(editing.LineEditError):
        editing.change_line_quantity(order=order, item=item, new_quantity=2, actor=None)


@pytest.mark.django_db
def test_remove_line_rejects_a_line_from_another_order() -> None:
    order = _pending_order(quantity=1, stock=10)
    other_order = _pending_order(quantity=1, stock=10)
    foreign_item = other_order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.remove_line(order=order, item=foreign_item, actor=None)


@pytest.mark.django_db
def test_remove_line_with_no_surviving_variant_skips_the_inventory_call() -> None:
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    editing.add_line(order=order, variant=extra_variant, quantity=1, actor=None)
    item = order.items.get(variant=extra_variant)
    extra_variant.delete()
    item.refresh_from_db()
    assert item.variant_id is None

    event = editing.remove_line(order=order, item=item, actor=None)

    assert not order.items.filter(pk=item.pk).exists()
    assert event.edit_type == OrderEditEvent.EditType.LINE_REMOVED


@pytest.mark.django_db
def test_add_line_rejects_zero_or_negative_quantity() -> None:
    order = _pending_order(quantity=1, stock=10)
    variant = ProductVariantFactory(stock_quantity=10)

    with pytest.raises(editing.LineEditError):
        editing.add_line(order=order, variant=variant, quantity=0, actor=None)


@pytest.mark.django_db
def test_add_line_rejects_an_inactive_variant() -> None:
    order = _pending_order(quantity=1, stock=10)
    variant = ProductVariantFactory(stock_quantity=10, is_active=False)

    with pytest.raises(editing.LineEditError):
        editing.add_line(order=order, variant=variant, quantity=1, actor=None)


@pytest.mark.django_db
def test_override_line_price_rejects_a_negative_price() -> None:
    order = _pending_order(quantity=1, stock=10)
    item = order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.override_line_price(
            order=order, item=item, new_unit_price=Decimal("-1.00"), actor=None
        )


@pytest.mark.django_db
def test_override_line_price_rejects_a_line_from_another_order() -> None:
    order = _pending_order(quantity=1, stock=10)
    other_order = _pending_order(quantity=1, stock=10)
    foreign_item = other_order.items.get()

    with pytest.raises(editing.LineEditError):
        editing.override_line_price(
            order=order, item=foreign_item, new_unit_price=Decimal("1.00"), actor=None
        )


@pytest.mark.django_db
def test_add_line_while_confirmed_consumes_stock_directly() -> None:
    order = _pending_order(quantity=1, stock=10)
    transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    new_variant = ProductVariantFactory(stock_quantity=10)

    editing.add_line(order=order, variant=new_variant, quantity=4, actor=None)

    new_variant.refresh_from_db()
    assert new_variant.stock_quantity == 6
    assert StockReservation.objects.filter(order=order, variant=new_variant).count() == 0
    assert order.items.filter(variant=new_variant, quantity=4).exists()


@pytest.mark.django_db
def test_remove_line_while_confirmed_restores_stock() -> None:
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    editing.add_line(order=order, variant=extra_variant, quantity=2, actor=None)
    order = transition_status(order=order, to_status=Status.CONFIRMED, actor=None)
    extra_variant.refresh_from_db()
    assert extra_variant.stock_quantity == 8
    item_to_remove = order.items.get(variant=extra_variant)

    editing.remove_line(order=order, item=item_to_remove, actor=None)

    extra_variant.refresh_from_db()
    assert extra_variant.stock_quantity == 10
