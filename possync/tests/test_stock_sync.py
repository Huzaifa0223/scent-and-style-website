"""POST /api/pos/sync/stock/ — the stock formula and its guard rails.

available = onHand - (web orders awaiting POS ack) - (active reservations)
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from catalog.models import ProductVariant
from inventory.models import InventoryAdjustment, StockReservation
from orders.factories import OrderFactory
from orders.models import Order
from possync.models import PosProduct, PosSyncState
from possync.tests.support import (
    POS_TOKEN,
    STOCK_URL,
    ack_url,
    item,
    mapped_variant,
    minutes_ago,
    post_json,
    snapshot,
    web_order,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("pos_token", "cutoff_long_ago")]


@pytest.fixture
def pos_token(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = POS_TOKEN


@pytest.fixture
def cutoff_long_ago(db) -> None:  # type: ignore[no-untyped-def]
    """Go-live was a year ago, so test orders (confirmed "now") are inside
    the window unless a test says otherwise."""
    PosSyncState.objects.update_or_create(
        pk=1, defaults={"orders_since": timezone.now() - timedelta(days=365)}
    )


def available(variant: ProductVariant) -> int:
    row = ProductVariant.objects.with_available_quantity().get(pk=variant.pk)
    return int(row.available_quantity)  # type: ignore[attr-defined]


def stock(variant: ProductVariant) -> int:
    variant.refresh_from_db()
    return variant.stock_quantity


def reserve(variant: ProductVariant, quantity: int) -> None:
    StockReservation.objects.create(
        variant=variant,
        order=OrderFactory(),
        quantity=quantity,
        expires_at=timezone.now() + timedelta(hours=1),
    )


# --- the formula ------------------------------------------------------------


def test_with_nothing_pending_stock_equals_on_hand(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 7)]))

    assert response.status_code == 200
    assert response.json() == {"applied": 1, "unchanged": 0, "unmapped": [], "oversold": []}
    assert (stock(variant), available(variant)) == (7, 7)


def test_unacknowledged_web_orders_are_subtracted(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 2)
    web_order(variant, 1)

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert (stock(variant), available(variant)) == (7, 7)


def test_active_reservations_are_subtracted_on_top(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 2)
    reserve(variant, 1)

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    # onHand 10 - 2 awaiting ack - 1 reserved
    assert stock(variant) == 8
    assert available(variant) == 7


def test_expired_reservations_do_not_count(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    StockReservation.objects.create(
        variant=variant,
        order=OrderFactory(),
        quantity=4,
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert available(variant) == 10


def test_acknowledging_stops_the_subtraction(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    order = web_order(variant, 2)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=minutes_ago(10)))
    assert stock(variant) == 8

    post_json(client, ack_url(order.pk), {"posSaleNumber": "S-2026-00123"})
    # The POS recorded the sale, so its on-hand fell by the same 2 units.
    post_json(client, STOCK_URL, snapshot([item("POS-1", 8)], at=minutes_ago(5)))

    assert stock(variant) == 8  # not 6: the order is no longer subtracted twice


@pytest.mark.parametrize(
    "status",
    [
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.READY_TO_DISPATCH,
        Order.Status.DISPATCHED,
        Order.Status.OUT_FOR_DELIVERY,
        Order.Status.DELIVERED,
        Order.Status.FAILED_DELIVERY,
    ],
)
def test_orders_past_confirmation_count(client, status) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3, status=status)

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert stock(variant) == 7


@pytest.mark.parametrize(
    "status",
    [
        Order.Status.PENDING_CONFIRMATION,  # covered by its reservation instead
        Order.Status.CANCELLED,
        Order.Status.RETURNED,
        Order.Status.EXPIRED,
    ],
)
def test_pending_cancelled_returned_and_expired_orders_do_not_count(client, status) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3, status=status)

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert stock(variant) == 10


def test_orders_confirmed_before_the_cutoff_are_not_subtracted(client) -> None:  # type: ignore[no-untyped-def]
    """Go-live safety: history will never be acknowledged, so it must never
    zero out stock on the first snapshot."""
    variant = mapped_variant("POS-1", stock=99)
    PosSyncState.objects.update(orders_since=timezone.now() - timedelta(days=1))
    web_order(variant, 5, confirmed_at=timezone.now() - timedelta(days=30))
    web_order(variant, 2)  # confirmed after the cutoff

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert stock(variant) == 8


def test_stock_never_goes_below_zero_and_oversold_is_reported(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 1)]))

    assert stock(variant) == 0
    assert response.json()["oversold"] == [{"sku": "POS-1", "short": 2}]
    state = PosSyncState.objects.get(pk=1)
    assert state.last_result["oversold"] == [{"sku": "POS-1", "short": 2}]


def test_a_negative_pos_count_is_clamped_not_rejected(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=5)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", -2)]))

    assert response.status_code == 200
    assert stock(variant) == 0


# --- movements, prices, unmapped -------------------------------------------


def test_a_movement_is_written_only_when_the_number_changes(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=5)

    first = post_json(client, STOCK_URL, snapshot([item("POS-1", 9)], at=minutes_ago(10)))
    second = post_json(client, STOCK_URL, snapshot([item("POS-1", 9)], at=minutes_ago(5)))

    assert first.json()["applied"] == 1
    assert second.json() == {"applied": 0, "unchanged": 1, "unmapped": [], "oversold": []}
    movements = InventoryAdjustment.objects.filter(variant=variant)
    assert movements.count() == 1
    movement = movements.get()
    assert movement.delta == 4
    assert movement.note.startswith("POS sync: 9 on hand")


def test_price_is_recorded_but_the_website_price_never_changes(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", price="1000.00")

    post_json(client, STOCK_URL, snapshot([item("POS-1", 3, price=1250.5)]))

    variant.refresh_from_db()
    assert variant.pos_price == Decimal("1250.50")
    assert variant.price == Decimal("1000.00")


def test_unmapped_skus_are_listed_and_remembered_never_guessed(client) -> None:  # type: ignore[no-untyped-def]
    mapped = mapped_variant("POS-1", stock=1)
    lookalike = mapped_variant(None, name="Khamrah Lookalike", stock=4)

    response = post_json(
        client, STOCK_URL, snapshot([item("POS-1", 2), item("NEW-9", 6, price=900)])
    )

    assert response.json()["unmapped"] == ["NEW-9"]
    assert stock(mapped) == 2
    assert stock(lookalike) == 4  # untouched
    remembered = PosProduct.objects.get(sku="NEW-9")
    assert remembered.price == Decimal("900.00")
    assert remembered.last_seen_at is not None
    assert PosProduct.objects.get(sku="POS-1").last_seen_at is not None


def test_not_online_products_are_not_reported_as_unmapped(client) -> None:  # type: ignore[no-untyped-def]
    PosProduct.objects.create(sku="WATCH-1", not_online=True)

    response = post_json(client, STOCK_URL, snapshot([item("WATCH-1", 3), item("NEW-9", 1)]))

    assert response.json()["unmapped"] == ["NEW-9"]


# --- ordering ---------------------------------------------------------------


def test_an_older_snapshot_cannot_roll_stock_back(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=0)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 5)], at=minutes_ago(1)))
    last = PosSyncState.objects.get(pk=1).last_snapshot_at

    late_retry = post_json(client, STOCK_URL, snapshot([item("POS-1", 99)], at=minutes_ago(30)))

    assert late_retry.status_code == 200
    assert late_retry.json() == {
        "applied": 0, "unchanged": 0, "unmapped": [], "oversold": [], "stale": True,
    }  # fmt: skip
    assert stock(variant) == 5
    assert PosSyncState.objects.get(pk=1).last_snapshot_at == last
    assert InventoryAdjustment.objects.filter(variant=variant).count() == 1


def test_resending_the_same_snapshot_is_safe(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=0)
    body = snapshot([item("POS-1", 4)], at=minutes_ago(2))

    first = post_json(client, STOCK_URL, body)
    again = post_json(client, STOCK_URL, body)

    assert first.json()["applied"] == 1
    assert again.json()["unchanged"] == 1
    assert "stale" not in again.json()
    assert stock(variant) == 4


def test_a_newer_snapshot_is_applied(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=0)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 4)], at=minutes_ago(10)))

    post_json(client, STOCK_URL, snapshot([item("POS-1", 6)], at=minutes_ago(1)))

    assert stock(variant) == 6


def test_naive_timestamps_are_read_as_shop_local_time(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=0)
    naive = (timezone.localtime() - timedelta(minutes=5)).replace(tzinfo=None).isoformat()

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 3)], at=naive))

    assert response.status_code == 200
    assert stock(variant) == 3


def test_a_snapshot_stamped_in_the_future_is_refused(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=1)
    future = (timezone.now() + timedelta(hours=5)).isoformat()

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 50)], at=future))

    assert response.status_code == 400
    assert response.json() == {"error": "snapshot_in_future"}
    assert stock(variant) == 1
    assert PosSyncState.objects.get(pk=1).last_snapshot_at is None


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (b"not json", "invalid_json"),
        (b"[1, 2]", "invalid_json"),
        ({"items": []}, "invalid_snapshot_at"),
        ({"snapshotAt": "yesterday", "items": []}, "invalid_snapshot_at"),
        ({"snapshotAt": "2026-01-01T00:00:00Z"}, "invalid_items"),
        ({"snapshotAt": "2026-01-01T00:00:00Z", "items": {"a": 1}}, "invalid_items"),
    ],
)
def test_malformed_requests_are_400(client, payload, error) -> None:  # type: ignore[no-untyped-def]
    response = post_json(client, STOCK_URL, payload)

    assert response.status_code == 400
    assert response.json()["error"] == error


@pytest.mark.parametrize(
    ("bad_item", "error"),
    [
        ("just a string", "invalid_item"),
        ({"onHand": 1}, "invalid_sku"),
        ({"sku": "  ", "onHand": 1}, "invalid_sku"),
        ({"sku": "A"}, "invalid_on_hand"),
        ({"sku": "A", "onHand": "7"}, "invalid_on_hand"),
        ({"sku": "A", "onHand": 1.5}, "invalid_on_hand"),
        ({"sku": "A", "onHand": True}, "invalid_on_hand"),
        ({"sku": "A", "onHand": 1, "priceRs": -1}, "invalid_price"),
        ({"sku": "A", "onHand": 1, "priceRs": "abc"}, "invalid_price"),
        ({"sku": "A", "onHand": 1, "priceRs": True}, "invalid_price"),
    ],
)
def test_one_bad_item_rejects_the_whole_snapshot_and_names_it(client, bad_item, error) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=1)
    body = snapshot([item("POS-1", 50), bad_item])

    response = post_json(client, STOCK_URL, body)

    assert response.status_code == 400
    assert response.json() == {"error": error, "index": 1}
    assert stock(variant) == 1  # nothing half-applied


def test_two_counts_for_one_sku_are_refused(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=1)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 5), item("POS-1", 9)]))

    assert response.status_code == 400
    assert response.json() == {"error": "duplicate_sku", "index": 1}
    assert stock(variant) == 1


def test_integral_floats_are_accepted_as_counts(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=0)
    payload = f'{{"snapshotAt": "{minutes_ago(1)}", "items": [{{"sku": "POS-1", "onHand": 7.0}}]}}'

    response = post_json(client, STOCK_URL, payload.encode())

    assert response.status_code == 200
    assert stock(variant) == 7


def test_a_body_over_the_cap_is_413(client) -> None:  # type: ignore[no-untyped-def]
    pad = "a" * (5 * 1024 * 1024 + 1)
    body = json.dumps({"snapshotAt": minutes_ago(1), "items": [], "pad": pad}).encode()

    response = post_json(client, STOCK_URL, body)

    assert response.status_code == 413
    assert response.json() == {"error": "payload_too_large"}


def test_an_empty_snapshot_is_valid(client) -> None:  # type: ignore[no-untyped-def]
    response = post_json(client, STOCK_URL, snapshot([]))

    assert response.status_code == 200
    assert response.json() == {"applied": 0, "unchanged": 0, "unmapped": [], "oversold": []}
