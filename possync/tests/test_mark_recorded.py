"""Owner-only "mark recorded": take one web order out of the awaiting-ack
count by hand, with a reason, audited."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import Order
from possync import services
from possync.models import PosMappingEvent, PosOrderAck, PosSyncState
from possync.tests.support import (
    POS_TOKEN,
    STOCK_URL,
    WEB_ORDERS_URL,
    ack_url,
    auth,
    item,
    mapped_variant,
    minutes_ago,
    post_json,
    snapshot,
    web_order,
)

PORTAL = "/admin-portal/pos/"
MARKED = PosMappingEvent.Action.ORDER_MARKED_RECORDED


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


def mark(client, order: Order, reason: str = "Counted in the 12 Oct stock-take"):  # type: ignore[no-untyped-def]
    return client.post(f"{PORTAL}orders/{order.pk}/mark-recorded/", {"reason": reason}, follow=True)


def stock(variant: ProductVariant) -> int:
    variant.refresh_from_db()
    return variant.stock_quantity


def listed_ids(client) -> list[int]:  # type: ignore[no-untyped-def]
    response = client.get(WEB_ORDERS_URL, secure=True, **auth())
    return [order["id"] for order in response.json()["orders"]]


# --- the action -------------------------------------------------------------


@pytest.mark.django_db
def test_marking_removes_the_order_from_the_awaiting_count_and_is_audited(client, owner) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 2)
    assert services.awaiting_ack_orders().count() == 1

    response = mark(client, order, "Sold over the counter, already out of POS stock")

    assert response.status_code == 200
    assert services.awaiting_ack_orders().count() == 0
    ack = PosOrderAck.objects.get(order=order)
    assert ack.source == PosOrderAck.Source.MANUAL
    assert ack.reason == "Sold over the counter, already out of POS stock"
    assert ack.marked_by == owner
    assert ack.pos_sale_number == ""
    event = PosMappingEvent.objects.get(action=MARKED)
    assert event.actor == owner
    assert order.order_number in event.note
    assert "Sold over the counter" in event.note


@pytest.mark.django_db
def test_the_order_leaves_the_pos_web_orders_list(client, owner) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1)
    assert listed_ids(client) == [order.pk]

    mark(client, order)

    assert listed_ids(client) == []


@pytest.mark.django_db
def test_its_units_stop_being_subtracted_at_the_next_snapshot(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=99)
    kept = web_order(variant, 1)
    marked = web_order(variant, 3)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=minutes_ago(10)))
    assert stock(variant) == 6  # 10 - 1 - 3

    mark(client, marked)
    post_json(client, STOCK_URL, snapshot([item("POS-1", 10)], at=minutes_ago(1)))

    assert stock(variant) == 9  # only `kept` (1) is still subtracted
    assert services.awaiting_ack_orders().get() == kept


# --- guard rails ------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("reason", ["", "   ", "no", "x" * 401])
def test_a_reason_is_required_and_bounded(client, owner, reason) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1)

    response = mark(client, order, reason)

    assert response.status_code == 200
    assert PosOrderAck.objects.count() == 0
    assert services.awaiting_ack_orders().count() == 1
    assert PosMappingEvent.objects.filter(action=MARKED).count() == 0
    assert b"reason" in response.content.lower()


@pytest.mark.django_db
def test_an_already_recorded_order_cannot_be_marked_again(client, owner) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1)
    mark(client, order, "First reason given")

    again = mark(client, order, "Second reason given")

    assert b"already recorded" in again.content
    assert PosOrderAck.objects.get(order=order).reason == "First reason given"
    assert PosMappingEvent.objects.filter(action=MARKED).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [Order.Status.PENDING_CONFIRMATION, Order.Status.CANCELLED, Order.Status.EXPIRED],
)
def test_an_order_not_waiting_for_the_pos_cannot_be_marked(client, owner, status) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1, status=status)

    response = mark(client, order)

    assert b"not waiting for the POS" in response.content
    assert PosOrderAck.objects.count() == 0


@pytest.mark.django_db
def test_staff_and_anonymous_cannot_mark_or_see_the_page(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1)
    url = f"{PORTAL}orders/{order.pk}/mark-recorded/"
    assert client.post(url, {"reason": "because"}).status_code == 302  # to login

    staff = django_user_model.objects.create_user("staff", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)

    assert client.get(PORTAL + "orders/").status_code == 403
    assert client.post(url, {"reason": "because"}).status_code == 403
    assert PosOrderAck.objects.count() == 0


@pytest.mark.django_db
def test_unknown_order_is_404(client, owner) -> None:  # type: ignore[no-untyped-def]
    response = client.post(f"{PORTAL}orders/999999/mark-recorded/", {"reason": "because yes"})

    assert response.status_code == 404


# --- interplay with the POS acknowledging it later -------------------------


@pytest.mark.django_db
def test_the_pos_can_still_acknowledge_a_manually_marked_order(client, owner) -> None:  # type: ignore[no-untyped-def]
    order = web_order(mapped_variant("POS-1"), 1)
    mark(client, order, "Marked while the POS was down")

    response = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-2026-00777"})

    assert response.status_code == 200
    assert response.json()["alreadyAcked"] is False
    ack = PosOrderAck.objects.get(order=order)
    assert (ack.source, ack.pos_sale_number) == (PosOrderAck.Source.POS, "S-2026-00777")
    assert ack.reason == "Marked while the POS was down"  # history kept
    # From here on it is a normal acknowledgement.
    same = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-2026-00777"})
    different = post_json(client, ack_url(order.pk), {"posSaleNumber": "S-other"})
    assert same.status_code == 200
    assert different.status_code == 409


# --- page -------------------------------------------------------------------


@pytest.mark.django_db
def test_the_page_lists_only_awaiting_orders_without_customer_details(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", name="Khamrah")
    waiting = web_order(variant, 2, customer_name="Ayesha Khan", customer_phone="+923001234567")
    web_order(variant, 1, status=Order.Status.CANCELLED)

    html = client.get(PORTAL + "orders/").content.decode()

    assert waiting.order_number in html
    assert re.search(r"\b2 \S Khamrah", html)  # "2 <times sign> Khamrah"
    assert "Ayesha" not in html and "923001234567" not in html
    assert html.count("Mark as recorded") == 1


@pytest.mark.django_db
def test_mapping_page_links_to_the_awaiting_orders(client, owner) -> None:  # type: ignore[no-untyped-def]
    web_order(mapped_variant("POS-1"), 1)

    html = client.get(PORTAL).content.decode()

    assert "Web orders awaiting the POS" in html
    assert f'href="{PORTAL}orders/"' in html
    assert "1 order(s)" in html
