"""POS_SYNC_SUBTRACT_WEB_ORDERS: read-only (default) vs subtracting.

Read-only: stock_quantity = max(onHand, 0); web orders are not subtracted and
"oversold" is not computed (reservations still are subtracted, by the existing
availability logic). The web-orders endpoints stay available in both modes.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import ProductVariant
from inventory.models import StockReservation
from orders.factories import OrderFactory
from possync.models import PosOrderAck, PosSyncState
from possync.tests.support import (
    POS_TOKEN,
    STOCK_URL,
    WEB_ORDERS_URL,
    ack_url,
    auth,
    item,
    mapped_variant,
    post_json,
    snapshot,
    web_order,
)

PORTAL = "/admin-portal/pos/"
READ_ONLY_NOTE = "Read-only mode — web orders are not subtracted"


@pytest.fixture(autouse=True)
def _config(settings, db) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = POS_TOKEN
    PosSyncState.objects.update_or_create(
        pk=1, defaults={"orders_since": timezone.now() - timedelta(days=365)}
    )


@pytest.fixture
def owner(client, django_user_model):  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_superuser("owner", "o@example.com", "pw-not-used")
    client.force_login(user)
    return user


def stock(variant: ProductVariant) -> int:
    variant.refresh_from_db()
    return variant.stock_quantity


def available(variant: ProductVariant) -> int:
    row = ProductVariant.objects.with_available_quantity().get(pk=variant.pk)
    return int(row.available_quantity)  # type: ignore[attr-defined]


def reserve(variant: ProductVariant, quantity: int) -> None:
    StockReservation.objects.create(
        variant=variant,
        order=OrderFactory(),
        quantity=quantity,
        expires_at=timezone.now() + timedelta(hours=1),
    )


# --- the default -------------------------------------------------------------


def test_the_default_is_read_only(settings) -> None:  # type: ignore[no-untyped-def]
    # The real configuration: nothing in .env turns subtraction on.
    assert settings.POS_SYNC_SUBTRACT_WEB_ORDERS is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("yes", True), ("false", False), ("0", False), ("", False)],
)
def test_env_parsing(monkeypatch, raw, expected) -> None:  # type: ignore[no-untyped-def]
    from config.settings.base import env

    monkeypatch.setenv("POS_SYNC_SUBTRACT_WEB_ORDERS", raw)

    assert env.bool("POS_SYNC_SUBTRACT_WEB_ORDERS", default=False) is expected


# --- read-only mode ---------------------------------------------------------


@pytest.mark.django_db
def test_read_only_stock_is_the_pos_on_hand(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3)  # confirmed, never acknowledged — must NOT be subtracted

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert response.status_code == 200
    assert stock(variant) == 10
    assert available(variant) == 10


@pytest.mark.django_db
def test_read_only_still_subtracts_active_reservations(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3)
    reserve(variant, 2)

    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert stock(variant) == 10
    assert available(variant) == 8  # onHand 10 - 2 reserved; the 3 are not subtracted


@pytest.mark.django_db
def test_read_only_never_reports_oversold(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 5)  # would be "short by 4" if it were subtracted

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 1)]))

    assert response.json()["oversold"] == []
    assert stock(variant) == 1
    assert PosSyncState.objects.get(pk=1).last_result["oversold"] == []


@pytest.mark.django_db
def test_read_only_clamps_a_negative_count_to_zero(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=5)

    post_json(client, STOCK_URL, snapshot([item("POS-1", -3)]))

    assert stock(variant) == 0


@pytest.mark.django_db
def test_read_only_still_records_prices_and_unmapped(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", price="1000.00")

    response = post_json(
        client, STOCK_URL, snapshot([item("POS-1", 4, price=1250), item("NEW-1", 2)])
    )

    variant.refresh_from_db()
    assert str(variant.pos_price) == "1250.00"
    assert str(variant.price) == "1000.00"
    assert response.json()["unmapped"] == ["NEW-1"]


@pytest.mark.django_db
def test_read_only_web_orders_endpoints_still_work(client) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    order = web_order(variant, 2)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    listed = client.get(WEB_ORDERS_URL, secure=True, **auth())
    acked = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-1"})
    after = client.get(WEB_ORDERS_URL, secure=True, **auth())

    assert [o["id"] for o in listed.json()["orders"]] == [order.pk]
    assert acked.status_code == 200
    assert PosOrderAck.objects.get(order=order).pos_sale_number == "S-1"
    assert after.json() == {"orders": []}
    assert stock(variant) == 10  # acknowledging changes nothing about stock in this mode


# --- subtracting mode (same data, other answer) ---------------------------


@pytest.mark.django_db
def test_subtracting_mode_gives_the_other_answer_on_the_same_data(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = True
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 3)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 10)]))

    assert stock(variant) == 7
    assert response.json()["oversold"] == []


@pytest.mark.django_db
def test_subtracting_mode_reports_oversold(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = True
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 5)

    response = post_json(client, STOCK_URL, snapshot([item("POS-1", 1)]))

    assert response.json()["oversold"] == [{"sku": "POS-1", "short": 4}]
    assert stock(variant) == 0


@pytest.mark.django_db
def test_switching_mode_takes_effect_on_the_next_snapshot(client, settings) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    web_order(variant, 4)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=_ago(10)))
    assert stock(variant) == 10

    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = True
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=_ago(5)))
    assert stock(variant) == 6

    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = False
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=_ago(1)))
    assert stock(variant) == 10


def _ago(minutes: int) -> str:
    return (timezone.now() - timedelta(minutes=minutes)).isoformat()


# --- portal ----------------------------------------------------------------


@pytest.mark.django_db
def test_mapping_page_shows_read_only_mode_at_the_top(client, owner) -> None:  # type: ignore[no-untyped-def]
    html = client.get(PORTAL).content.decode()

    assert 'data-pos-mode="read-only"' in html
    assert "Mode: read-only" in html
    assert 'data-pos-mode="subtract"' not in html
    # at the top: before the page heading and the sync status panel
    assert html.index("data-pos-mode") < html.index("POS mapping</h1>")
    assert html.index("data-pos-mode") < html.index("Sync status")


@pytest.mark.django_db
def test_mapping_page_shows_subtracting_mode_when_on(client, owner, settings) -> None:  # type: ignore[no-untyped-def]
    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = True

    html = client.get(PORTAL).content.decode()

    assert 'data-pos-mode="subtract"' in html
    assert "Mode: subtracting web orders" in html
    assert 'data-pos-mode="read-only"' not in html


@pytest.mark.django_db
def test_awaiting_orders_page_notes_read_only_mode(client, owner) -> None:  # type: ignore[no-untyped-def]
    web_order(mapped_variant("POS-1"), 1)

    html = client.get(PORTAL + "orders/").content.decode()

    assert READ_ONLY_NOTE in html


@pytest.mark.django_db
def test_awaiting_orders_page_has_no_note_when_subtracting(client, owner, settings) -> None:  # type: ignore[no-untyped-def]
    settings.POS_SYNC_SUBTRACT_WEB_ORDERS = True

    assert READ_ONLY_NOTE not in client.get(PORTAL + "orders/").content.decode()


@pytest.mark.django_db
def test_json_body_shape_is_identical_in_both_modes(client, settings) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("POS-1", stock=0)
    shapes = []
    for flag in (False, True):
        settings.POS_SYNC_SUBTRACT_WEB_ORDERS = flag
        body = post_json(client, STOCK_URL, snapshot([item("POS-1", 1)])).content
        shapes.append(sorted(json.loads(body)))

    assert shapes[0] == shapes[1] == ["applied", "oversold", "skipped", "unchanged", "unmapped"]
