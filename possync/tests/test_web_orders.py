"""GET /api/pos/sync/web-orders/ and POST …/<id>/ack/."""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import Order
from possync.models import PosOrderAck, PosSyncState
from possync.tests.support import (
    POS_TOKEN,
    WEB_ORDERS_URL,
    ack_url,
    auth,
    mapped_variant,
    post_json,
    web_order,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("pos_token", "cutoff_long_ago")]

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@pytest.fixture
def pos_token(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = POS_TOKEN


@pytest.fixture
def cutoff_long_ago(db) -> None:  # type: ignore[no-untyped-def]
    PosSyncState.objects.update_or_create(
        pk=1, defaults={"orders_since": timezone.now() - timedelta(days=365)}
    )


def listed(client):  # type: ignore[no-untyped-def]
    response = client.get(WEB_ORDERS_URL, secure=True, **auth())
    assert response.status_code == 200
    return response.json()["orders"]


# --- listing ----------------------------------------------------------------


def test_shape_and_mapped_vs_unmapped_lines(client) -> None:  # type: ignore[no-untyped-def]
    mapped = mapped_variant("ARM-CDN", price="12500.00", name="Club De Nuit")
    unmapped = mapped_variant(None, price="3000.50", name="Loose Perfume")
    order = web_order(mapped, 2)
    from orders.factories import OrderItemFactory

    OrderItemFactory(
        order=order,
        variant=unmapped,
        quantity=1,
        unit_price=unmapped.price,
        product_name="Loose Perfume",
    )

    (entry,) = listed(client)

    assert set(entry) == {"id", "number", "paidAt", "lines", "unmappedLines"}
    assert entry["id"] == order.pk
    assert entry["number"] == order.order_number
    assert ISO_Z.match(entry["paidAt"])
    assert entry["lines"] == [
        {
            "posSku": "ARM-CDN",
            "variantSku": mapped.sku,
            "name": "Club De Nuit",
            "qty": 2,
            "unitPriceRs": 12500,
        }
    ]
    assert entry["unmappedLines"] == [
        {
            "posSku": None,
            "variantSku": unmapped.sku,
            "name": "Loose Perfume",
            "qty": 1,
            "unitPriceRs": 3000.5,
        }
    ]


def test_no_customer_data_is_ever_included(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    web_order(
        variant,
        1,
        customer_name="Ayesha Khan",
        customer_phone="+923001234567",
        customer_whatsapp_number="+923007654321",
        customer_email="ayesha.khan@example.com",
        delivery_address="House 9, Street 4, Gulshan",
        delivery_city="Karachi",
        customer_notes="Please gift wrap",
        merchant_notes="VIP",
    )

    response = client.get(WEB_ORDERS_URL, secure=True, **auth())

    body = response.content.decode()
    for private in (
        "Ayesha", "Khan", "923001234567", "923007654321", "example.com",
        "Gulshan", "Karachi", "gift wrap", "VIP",
    ):  # fmt: skip
        assert private not in body
    assert set(response.json()["orders"][0]) == {"id", "number", "paidAt", "lines", "unmappedLines"}


@pytest.mark.parametrize(
    "status",
    [Order.Status.PENDING_CONFIRMATION, Order.Status.CANCELLED, Order.Status.EXPIRED],
)
def test_only_orders_the_pos_should_record_are_listed(client, status) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    web_order(variant, 1, status=status)
    live = web_order(variant, 1)

    assert [o["id"] for o in listed(client)] == [live.pk]


def test_orders_before_the_cutoff_are_not_listed(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    PosSyncState.objects.update(orders_since=timezone.now() - timedelta(days=1))
    web_order(variant, 1, confirmed_at=timezone.now() - timedelta(days=10))
    recent = web_order(variant, 1)

    assert [o["id"] for o in listed(client)] == [recent.pk]


def test_oldest_confirmation_comes_first(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    now = timezone.now()
    newer = web_order(variant, 1, confirmed_at=now - timedelta(hours=1))
    older = web_order(variant, 1, confirmed_at=now - timedelta(hours=5))

    assert [o["id"] for o in listed(client)] == [older.pk, newer.pk]


def test_empty_when_nothing_is_waiting(client) -> None:  # type: ignore[no-untyped-def]
    assert listed(client) == []


def test_listing_is_a_constant_number_of_queries(client, django_assert_max_num_queries) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    for _ in range(8):
        web_order(variant, 1)

    with django_assert_max_num_queries(8):
        assert len(listed(client)) == 8


# --- acknowledgement --------------------------------------------------------


def test_ack_records_the_sale_and_removes_the_order_from_the_list(client) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("ARM-1"), 1)

    response = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-2026-00123"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "orderId": order.pk,
        "posSaleNumber": "S-2026-00123",
        "alreadyAcked": False,
    }
    assert PosOrderAck.objects.get(order=order).pos_sale_number == "S-2026-00123"
    assert listed(client) == []


def test_ack_is_idempotent_for_the_same_sale_number(client) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("ARM-1"), 1)
    post_json(client, ack_url(order.pk), {"posSaleNumber": "S-1"})

    again = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-1"})

    assert again.status_code == 200
    assert again.json()["alreadyAcked"] is True
    assert PosOrderAck.objects.filter(order=order).count() == 1


def test_a_different_sale_number_is_a_409_and_changes_nothing(client) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("ARM-1"), 1)
    post_json(client, ack_url(order.pk), {"posSaleNumber": "S-1"})

    conflict = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-2"})

    assert conflict.status_code == 409
    assert conflict.json() == {"error": "already_acked_differently", "posSaleNumber": "S-1"}
    assert PosOrderAck.objects.get(order=order).pos_sale_number == "S-1"


def test_unknown_order_is_404(client) -> None:  # type: ignore[no-untyped-def]
    response = post_json(client, ack_url(999999), {"posSaleNumber": "S-1"})

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


@pytest.mark.parametrize(
    "payload", [{}, {"posSaleNumber": ""}, {"posSaleNumber": "   "}, {"posSaleNumber": 123},
                {"posSaleNumber": "x" * 65}],
)  # fmt: skip
def test_bad_sale_numbers_are_400(client, payload) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("ARM-1"), 1)

    response = post_json(client, ack_url(order.pk), payload)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_pos_sale_number"}
    assert PosOrderAck.objects.count() == 0


def test_an_order_not_awaiting_the_pos_cannot_be_acked(client) -> None:  # type: ignore[no-untyped-def]
    cancelled = web_order(mapped_variant("ARM-1"), 1, status=Order.Status.CANCELLED)

    response = post_json(client, ack_url(cancelled.pk), {"posSaleNumber": "S-1"})

    assert response.status_code == 409
    assert response.json() == {"error": "order_not_awaiting_ack", "status": "cancelled"}
    assert PosOrderAck.objects.count() == 0


def test_acking_does_not_touch_stock_or_prices(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1", stock=7, price="1500.00")
    order = web_order(variant, 2)

    post_json(client, ack_url(order.pk), {"posSaleNumber": "S-1"})

    reloaded = ProductVariant.objects.get(pk=variant.pk)
    assert (reloaded.stock_quantity, reloaded.price) == (7, Decimal("1500.00"))
