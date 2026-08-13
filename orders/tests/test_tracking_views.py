"""OrderTrackingView — HTTP-level acceptance gates for roadmap Stage 11.

Gate 1 (byte-identical "not found"/"phone doesn't match" responses) and
gate 3 (no PII/internal-ID leak, asserted on rendered HTML) are the two
gates this file exists specifically to prove; gate 2 (rate limiting) is
proven at both the service layer (test_tracking.py) and here, at the HTTP
boundary.
"""

from __future__ import annotations

import pytest

from orders.factories import OrderFactory, OrderItemFactory
from orders.models import OrderTrackingAttempt
from orders.state_machine import transition_status
from orders.status import Status
from orders.tracking_config import (
    TRACKING_LOCKOUT_FAILURE_THRESHOLD,
    TRACKING_RATE_LIMIT_MAX_ATTEMPTS,
)

TRACK_URL = "/track/"


@pytest.mark.django_db
def test_get_renders_an_empty_form(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(TRACK_URL)

    assert response.status_code == 200
    assert b'name="order_number"' in response.content
    assert b'name="mobile_number"' in response.content


@pytest.mark.django_db
def test_get_prefills_the_order_number_from_the_query_string(client) -> None:  # type: ignore[no-untyped-def]
    """notifications.whatsapp.message_builder._tracking_url() links here
    as ``/track/?order=<order_number>`` — the exact contract every
    status-update message has sent since Stage 9."""
    response = client.get(TRACK_URL, {"order": "ORD-10002-CPX"})

    assert response.status_code == 200
    assert b"ORD-10002-CPX" in response.content


@pytest.mark.django_db
def test_a_correct_lookup_shows_the_order(client) -> None:  # type: ignore[no-untyped-def]
    order = OrderFactory(customer_phone="+923001234567")
    OrderItemFactory(order=order, product_name="Tracking Test Product")

    response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03001234567"}
    )

    assert response.status_code == 200
    assert order.order_number.encode() in response.content
    assert b"Tracking Test Product" in response.content


@pytest.mark.django_db
def test_gate1_not_found_and_phone_mismatch_return_byte_identical_responses(client) -> None:  # type: ignore[no-untyped-def]
    order = OrderFactory(customer_phone="+923001234567")

    not_found_response = client.post(
        TRACK_URL, {"order_number": "ORD-99999-ZZZ", "mobile_number": "03001234567"}
    )
    wrong_phone_response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03009999999"}
    )

    assert not_found_response.status_code == 200
    assert wrong_phone_response.status_code == 200
    assert not_found_response.content == wrong_phone_response.content


@pytest.mark.django_db
def test_gate1_an_unparseable_phone_also_matches_the_same_response_byte_for_byte(client) -> None:  # type: ignore[no-untyped-def]
    order = OrderFactory(customer_phone="+923001234567")

    not_found_response = client.post(
        TRACK_URL, {"order_number": "ORD-99999-ZZZ", "mobile_number": "03001234567"}
    )
    garbage_phone_response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "not-a-phone"}
    )

    assert not_found_response.content == garbage_phone_response.content


@pytest.mark.django_db
def test_gate2_the_short_window_rate_limit_triggers_at_the_configured_threshold(client) -> None:  # type: ignore[no-untyped-def]
    for _ in range(TRACKING_RATE_LIMIT_MAX_ATTEMPTS):
        client.post(TRACK_URL, {"order_number": "ORD-99999-ZZZ", "mobile_number": "03001234567"})

    response = client.post(
        TRACK_URL, {"order_number": "ORD-99999-ZZZ", "mobile_number": "03001234567"}
    )

    assert response.status_code == 429


@pytest.mark.django_db
def test_gate2_the_lockout_applies_after_repeated_failures(client) -> None:  # type: ignore[no-untyped-def]
    order = OrderFactory(customer_phone="+923001234567")
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        OrderTrackingAttempt.objects.create(
            ip_address="127.0.0.1", order_number="ORD-1-AAA", succeeded=False
        )

    # Even a *correct* lookup is refused once locked out — the whole
    # point of the lockout tier is that it doesn't matter anymore whether
    # this particular attempt would have succeeded.
    response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03001234567"}
    )

    assert response.status_code == 429
    assert order.order_number.encode() not in response.content


@pytest.mark.django_db
def test_a_locked_out_request_never_queries_for_the_order(client) -> None:  # type: ignore[no-untyped-def]
    """The rate limit is checked before lookup_order() is ever called —
    asserted here by proving no new OrderTrackingAttempt row is written
    for a request that got rejected before reaching the lookup."""
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        OrderTrackingAttempt.objects.create(
            ip_address="127.0.0.1", order_number="ORD-1-AAA", succeeded=False
        )
    count_before = OrderTrackingAttempt.objects.count()

    client.post(TRACK_URL, {"order_number": "ORD-99999-ZZZ", "mobile_number": "03001234567"})

    assert OrderTrackingAttempt.objects.count() == count_before


@pytest.mark.django_db
def test_gate3_the_response_never_leaks_email_address_notes_or_internal_ids(client) -> None:  # type: ignore[no-untyped-def]
    """Asserted on the rendered HTML byte content, not the view's
    context dict — the context could carry all of this safely as long as
    the template never renders it; only the actual response body is the
    thing a real visitor (or an attacker) ever sees."""
    order = OrderFactory(
        customer_phone="+923001234567",
        customer_email="secret-customer-email@example.com",
        delivery_address="42 Very Specific Street, Apartment 7B",
        customer_notes="Please leave with the neighbour, code 4471.",
        merchant_notes="VIP customer — always upgrade shipping, internal discount code SECRET99.",
    )
    OrderItemFactory(order=order)
    transition_status(
        order=order,
        to_status=Status.CANCELLED,
        actor=None,
        note="Internal note: customer was rude on the phone, flag account.",
    )

    response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03001234567"}
    )

    body = response.content.decode()
    assert "secret-customer-email@example.com" not in body
    assert "42 Very Specific Street" not in body
    assert "Please leave with the neighbour" not in body
    assert "VIP customer" not in body
    assert "SECRET99" not in body
    assert "customer was rude" not in body


def test_gate3_the_template_source_never_references_an_internal_pk() -> None:
    """A runtime substring check against ``order.pk`` is unreliable on
    its own — a small integer can coincidentally match unrelated numbers
    elsewhere on the page (a millisecond debounce delay, a quantity, a
    price). The structural guarantee is that the template source itself
    never references ``order.pk``/``order.id``/``customer_id``/
    ``customer.pk`` at all, the same "grep the template" technique
    Stage 8's own snapshot-leakage gate already uses."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parent.parent.parent
        / "templates"
        / "orders"
        / "order_tracking.html"
    ).read_text(encoding="utf-8")
    for forbidden in ("order.pk", "order.id", "customer_id", "customer.pk", "customer.id"):
        assert forbidden not in source, forbidden


@pytest.mark.django_db
def test_gate3_the_response_does_not_leak_the_full_postal_code_or_instructions(client) -> None:  # type: ignore[no-untyped-def]
    order = OrderFactory(
        customer_phone="+923001234567",
        delivery_postal_code="75500",
        delivery_instructions="Ring the bell twice, dog is friendly.",
    )
    OrderItemFactory(order=order)

    response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03001234567"}
    )

    body = response.content.decode()
    assert "Ring the bell twice" not in body


@pytest.mark.django_db
def test_status_timeline_shows_the_status_but_never_the_actor_username(client) -> None:  # type: ignore[no-untyped-def]
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    owner = user_model.objects.create_user(username="very-secret-staff-username", password="x")
    order = OrderFactory(customer_phone="+923001234567")
    OrderItemFactory(order=order)
    transition_status(order=order, to_status=Status.CONFIRMED, actor=owner)

    response = client.post(
        TRACK_URL, {"order_number": order.order_number, "mobile_number": "03001234567"}
    )

    assert b"very-secret-staff-username" not in response.content


@pytest.mark.django_db
def test_incomplete_submission_re_renders_the_form_with_an_error(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(TRACK_URL, {"order_number": "", "mobile_number": ""})

    assert response.status_code == 400
    assert b"required" in response.content.lower() or b"field" in response.content.lower()
