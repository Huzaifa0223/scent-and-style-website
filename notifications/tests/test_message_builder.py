"""notifications.whatsapp.message_builder — roadmap Stage 9 gate 1 and the
snapshot discipline it must inherit from Stage 8.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from notifications.whatsapp import message_builder
from orders.factories import OrderFactory
from orders.models import Order, OrderItem
from store.models import StoreSettings


def _configure_site_url() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.site_url = "https://mystore.pk"
    settings_obj.save()


def _add_items(order: Order, count: int) -> None:
    for i in range(count):
        OrderItem.objects.create(
            order=order,
            product_name=f"Product {i}",
            variant_label=f"Variant {i}",
            sku=f"SKU-{i:04d}",
            unit_price=Decimal("100.00"),
            quantity=1,
            line_total=Decimal("100.00"),
        )


@pytest.mark.django_db
def test_confirmation_message_includes_every_item_when_under_budget() -> None:
    _configure_site_url()
    order = OrderFactory(order_number="ORD-10000-ABC")
    _add_items(order, 3)

    message = message_builder.build_order_confirmation_message(order)

    assert "ORD-10000-ABC" in message
    assert "Product 0" in message
    assert "Product 1" in message
    assert "Product 2" in message
    assert "more item" not in message
    assert "https://mystore.pk/track/?order=ORD-10000-ABC" in message


@pytest.mark.django_db
def test_confirmation_message_reads_only_orderitem_snapshot_fields() -> None:
    """Same snapshot discipline Stage 8 enforces for order templates,
    extended to WhatsApp text: renaming/repricing/deleting the underlying
    product must not change the message."""
    order = OrderFactory()
    item = OrderItem.objects.create(
        order=order,
        product_name="Original Name",
        variant_label="Red / 50ml",
        sku="SKU-0001",
        unit_price=Decimal("500.00"),
        quantity=2,
        line_total=Decimal("1000.00"),
    )
    assert item.variant_id is None  # no catalog object ever existed for this snapshot

    message = message_builder.build_order_confirmation_message(order)

    assert "Original Name" in message
    assert "Rs. 1,000.00" in message  # line_total, the snapshot — not unit_price re-derived


@pytest.mark.django_db
def test_gate1_a_30_item_order_truncates_within_budget_with_notice_and_tracking_url() -> None:
    """Gate 1."""
    _configure_site_url()
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_message_max_chars = 500
    settings_obj.save()
    order = OrderFactory(order_number="ORD-10000-XYZ")
    _add_items(order, 30)

    message = message_builder.build_order_confirmation_message(order)

    assert len(message) <= 500
    assert "more item" in message
    assert "https://mystore.pk/track/?order=ORD-10000-XYZ" in message
    # The tail of the message (totals/delivery/tracking) must always
    # survive truncation — only the itemised list shrinks.
    assert "Subtotal" in message
    assert "Total" in message
    assert "Deliver to" in message


@pytest.mark.django_db
def test_a_30_item_order_under_a_generous_budget_is_not_truncated() -> None:
    _configure_site_url()
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_message_max_chars = 10_000
    settings_obj.save()
    order = OrderFactory()
    _add_items(order, 30)

    message = message_builder.build_order_confirmation_message(order)

    assert "more item" not in message
    for i in range(30):
        assert f"Product {i}" in message


@pytest.mark.django_db
def test_tracking_url_is_omitted_when_site_url_is_not_configured() -> None:
    order = OrderFactory()
    _add_items(order, 1)

    message = message_builder.build_order_confirmation_message(order)

    assert "Track your order" not in message


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.DISPATCHED,
        Order.Status.OUT_FOR_DELIVERY,
        Order.Status.DELIVERED,
        Order.Status.CANCELLED,
    ],
)
def test_build_status_update_message_renders_for_every_templated_status(status: str) -> None:
    order = OrderFactory(
        order_number="ORD-10000-DEF",
        customer_name="Ayesha Khan",
        status=status,
        tracking_number="TRK123",
        courier_name="TCS",
    )

    message = message_builder.build_status_update_message(order)

    assert "Ayesha Khan" in message
    assert "ORD-10000-DEF" in message


@pytest.mark.django_db
def test_build_status_update_message_raises_for_a_status_with_no_template() -> None:
    order = OrderFactory(status=Order.Status.READY_TO_DISPATCH)

    with pytest.raises(ValueError, match="No WhatsApp template"):
        message_builder.build_status_update_message(order)


@pytest.mark.django_db
def test_build_status_update_message_tolerates_an_unrecognised_placeholder() -> None:
    """A merchant hand-editing a template in Django admin can typo a
    placeholder name — must degrade to an empty string, not 500."""
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_template_confirmed = "Hi {customer_name}, see {not_a_real_placeholder}."
    settings_obj.save()
    order = OrderFactory(status=Order.Status.CONFIRMED, customer_name="Ayesha")

    message = message_builder.build_status_update_message(order)

    assert message == "Hi Ayesha, see ."


@pytest.mark.django_db
def test_a_budget_too_small_even_for_a_zero_item_order_degrades_without_crashing() -> None:
    """Reachable, not just a theoretical edge case: a merchant can set
    whatsapp_message_max_chars right at its validator floor (200), and a
    long delivery address alone can make even a zero-item order's
    header+footer exceed that. The truncation loop has nothing to trim
    in that case (zero items) — this proves it returns the full message
    honestly rather than crashing, infinite-looping, or silently
    producing an empty string."""
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_message_max_chars = 200
    settings_obj.save()
    order = OrderFactory(
        delivery_address="A" * 250,
        delivery_city="Karachi",
    )
    # Deliberately zero OrderItems — nothing for the truncation loop to trim.

    message = message_builder.build_order_confirmation_message(order)

    assert "A" * 250 in message
    assert len(message) > 200  # honestly over budget, not silently truncated to nothing
