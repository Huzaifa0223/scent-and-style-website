"""HTTP-level tests for the checkout flow (roadmap Stage 8)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from catalog.factories import ProductFactory
from core.models import RateLimitAttempt, RateLimitScope
from core.ratelimit import CHECKOUT_RATE_LIMIT_POLICY, record_attempt
from orders.models import Order
from orders.services import EmptyCartError
from store.models import DeliveryStrategy, StoreSettings

CHECKOUT_URL = "/checkout/"


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


def _checkout_post_data(**overrides: str) -> dict[str, str]:
    defaults = {
        "name": "Ayesha Khan",
        "mobile_number": "03001234567",
        "same_as_mobile": "on",
        "email": "ayesha@example.com",
        "address": "House 1, Street 2",
        "city": "Karachi",
        "postal_code": "75500",
        "instructions": "Leave at the gate",
        "notes": "",
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.django_db
def test_checkout_get_with_an_empty_cart_redirects_to_the_listing(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(CHECKOUT_URL)

    assert response.status_code == 302
    assert response.url == "/products/"


@pytest.mark.django_db
def test_checkout_get_with_items_renders_the_form(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.get(CHECKOUT_URL)

    assert response.status_code == 200
    assert b'name="mobile_number"' in response.content
    assert variant.product.name.encode() in response.content


@pytest.mark.django_db
def test_checkout_post_creates_an_order_and_redirects_to_confirmation(client) -> None:  # type: ignore[no-untyped-def]
    _flat_rate_delivery(Decimal("100.00"))
    variant = _variant_with_stock(5, price=Decimal("250.00"))
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 2})

    response = client.post(CHECKOUT_URL, _checkout_post_data())

    order = Order.objects.get()
    assert response.status_code == 302
    assert response.url == f"/orders/{order.order_number}/confirmation/"
    assert order.customer_name == "Ayesha Khan"
    assert order.customer_phone == "+923001234567"
    assert order.customer_whatsapp_number == "+923001234567"
    assert order.subtotal == Decimal("500.00")
    assert order.delivery_charge == Decimal("100.00")


@pytest.mark.django_db
def test_gate2_the_order_exists_before_and_independent_of_any_whatsapp_interaction(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """Gate 2 — the order exists and is queryable the moment checkout's
    POST returns, before the confirmation page (and the WhatsApp link it
    builds) is ever requested or rendered. No portal order list exists
    yet to check "visible in the portal" through (Stage 10's job); this
    is the structural guarantee that gate actually depends on —
    orders.services.create_order() commits before any WhatsApp string is
    even constructed, and construction lives entirely in
    OrderConfirmationView.get(), a separate, later request."""
    _flat_rate_delivery()
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    checkout_response = client.post(CHECKOUT_URL, _checkout_post_data())

    # The order is fully committed here — the confirmation page (and the
    # WhatsApp message/link it builds) has not been requested at all yet.
    order = Order.objects.get()
    assert order.order_number in checkout_response.url
    assert order.status == Order.Status.PENDING_CONFIRMATION


@pytest.mark.django_db
def test_checkout_post_clears_the_cart_so_a_resubmit_finds_it_empty(client) -> None:  # type: ignore[no-untyped-def]
    _flat_rate_delivery()
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    client.post(CHECKOUT_URL, _checkout_post_data())
    assert Order.objects.count() == 1

    second_response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert Order.objects.count() == 1  # nothing new was created
    assert second_response.status_code == 302
    assert second_response.url == "/products/"


@pytest.mark.django_db
def test_checkout_post_with_an_invalid_mobile_number_re_renders_with_an_error(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.post(CHECKOUT_URL, _checkout_post_data(mobile_number="not-a-number"))

    assert response.status_code == 200
    assert Order.objects.count() == 0
    assert b"valid Pakistani mobile number" in response.content


@pytest.mark.django_db
def test_gate37_an_invalid_field_is_linked_to_its_error_via_aria_describedby(client) -> None:  # type: ignore[no-untyped-def]
    """§37: "Error messages associated with their inputs via
    aria-describedby." The input's own aria-describedby value must match
    a real element id actually present in the response — not just that
    the attribute exists somewhere, and not just that the error text is
    rendered somewhere on the page."""
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.post(CHECKOUT_URL, _checkout_post_data(mobile_number="not-a-number"))

    body = response.content.decode()
    assert 'aria-describedby="id_mobile_number-error"' in body
    assert 'id="id_mobile_number-error"' in body


@pytest.mark.django_db
def test_checkout_post_without_same_as_mobile_requires_a_whatsapp_number(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.post(CHECKOUT_URL, _checkout_post_data(same_as_mobile="", whatsapp_number=""))

    assert response.status_code == 200
    assert Order.objects.count() == 0
    assert b"same as mobile" in response.content


@pytest.mark.django_db
def test_checkout_post_with_an_invalid_whatsapp_number_re_renders_with_an_error(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.post(
        CHECKOUT_URL,
        _checkout_post_data(same_as_mobile="", whatsapp_number="not-a-number"),
    )

    assert response.status_code == 200
    assert Order.objects.count() == 0
    assert b"valid Pakistani mobile number" in response.content


@pytest.mark.django_db
def test_checkout_post_with_a_stock_shortfall_shows_the_per_line_error_and_creates_nothing(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """Gate 4, at the HTTP layer."""
    variant = _variant_with_stock(2, price=Decimal("100.00"))
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 2})
    variant.stock_quantity = 1
    variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert response.status_code == 200
    assert Order.objects.count() == 0
    assert variant.product.name.encode() in response.content
    assert b"only" in response.content.lower()


@pytest.mark.django_db
def test_confirmation_404s_for_a_session_that_never_placed_an_order(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/orders/ORD-10000-XXX/confirmation/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_confirmation_404s_for_the_wrong_order_number_even_with_a_valid_session(client) -> None:  # type: ignore[no-untyped-def]
    """Confirms the confirmation page is scoped to the exact order this
    session just placed, not any order number typed into the URL."""
    _flat_rate_delivery()
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    client.post(CHECKOUT_URL, _checkout_post_data())
    real_order = Order.objects.get()

    response = client.get(f"/orders/{real_order.order_number}9/confirmation/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_confirmation_renders_the_order_after_a_successful_checkout(client) -> None:  # type: ignore[no-untyped-def]
    _flat_rate_delivery()
    variant = _variant_with_stock(5, price=Decimal("300.00"))
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    checkout_response = client.post(CHECKOUT_URL, _checkout_post_data())
    order = Order.objects.get()

    response = client.get(checkout_response.url)

    assert response.status_code == 200
    assert order.order_number.encode() in response.content
    assert variant.product.name.encode() in response.content


@pytest.mark.django_db
def test_confirmation_page_always_has_the_order_details_message_in_the_rendered_html(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """Gate 4's actual point: the message text must be recoverable even
    if every JS path on the page fails — the Django test client never
    executes JavaScript at all, so this is already the no-JS case for
    content presence. Asserted against the visible <textarea>, not a
    JSON blob only script code could reach."""
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_number = "+923009999999"
    settings_obj.save()
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    checkout_response = client.post(CHECKOUT_URL, _checkout_post_data())
    order = Order.objects.get()

    response = client.get(checkout_response.url)

    assert response.status_code == 200
    assert b'id="whatsapp-message-text"' in response.content
    assert order.order_number.encode() in response.content
    assert variant.product.name.encode() in response.content
    assert b'id="whatsapp-link"' in response.content


@pytest.mark.django_db
def test_confirmation_page_omits_the_whatsapp_button_when_the_merchant_number_is_unconfigured(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """StoreSettings.whatsapp_number defaults to blank — building a
    WhatsApp deep link with no recipient would open WhatsApp addressed to
    nobody in particular, which can't do what this button exists to do.
    The order number and the copyable message text must still be
    there."""
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    checkout_response = client.post(CHECKOUT_URL, _checkout_post_data())
    order = Order.objects.get()

    response = client.get(checkout_response.url)

    assert response.status_code == 200
    assert b'id="whatsapp-link"' not in response.content
    assert order.order_number.encode() in response.content
    assert b'id="whatsapp-message-text"' in response.content


@pytest.mark.django_db
def test_checkout_post_handles_the_cart_emptying_between_the_view_check_and_create_order(
    client,
) -> None:  # type: ignore[no-untyped-def]
    """CheckoutView already refuses an empty cart before calling
    create_order() — this is the defensive branch for the narrow race
    where the cart empties in between (e.g. a second tab clearing it
    concurrently), simulated directly since it isn't reproducible from a
    single-threaded HTTP test."""
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    with patch("orders.views.create_order", side_effect=EmptyCartError):
        response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert response.status_code == 302
    assert response.url == "/products/"
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_post_with_a_distinct_whatsapp_number_uses_it_not_the_mobile_number(
    client,
) -> None:  # type: ignore[no-untyped-def]
    _flat_rate_delivery()
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    client.post(
        CHECKOUT_URL,
        _checkout_post_data(same_as_mobile="", whatsapp_number="03019876543"),
    )

    order = Order.objects.get()
    assert order.customer_phone == "+923001234567"
    assert order.customer_whatsapp_number == "+923019876543"


@pytest.mark.django_db
def test_gate3_repeated_checkout_submissions_are_rate_limited(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    for _ in range(CHECKOUT_RATE_LIMIT_POLICY.max_attempts):
        record_attempt(scope=RateLimitScope.CHECKOUT, ip_address="127.0.0.1", succeeded=True)

    response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert response.status_code == 429
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_repeated_invalid_checkout_submissions_lock_out_further_attempts(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    for _ in range(CHECKOUT_RATE_LIMIT_POLICY.lockout_failure_threshold):  # type: ignore[arg-type]
        record_attempt(scope=RateLimitScope.CHECKOUT, ip_address="127.0.0.1", succeeded=False)

    response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert response.status_code == 429
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_a_validation_failure_at_checkout_is_recorded_as_a_failed_ratelimit_attempt(
    client,
) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    client.post(CHECKOUT_URL, _checkout_post_data(mobile_number="not-a-phone-number"))

    attempt = RateLimitAttempt.objects.get(scope=RateLimitScope.CHECKOUT)
    assert attempt.succeeded is False


@pytest.mark.django_db
def test_a_successful_checkout_is_recorded_as_a_succeeded_ratelimit_attempt(client) -> None:  # type: ignore[no-untyped-def]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    client.post(CHECKOUT_URL, _checkout_post_data())

    attempt = RateLimitAttempt.objects.get(scope=RateLimitScope.CHECKOUT)
    assert attempt.succeeded is True


@pytest.mark.django_db
def test_gate5_a_checkout_error_report_does_not_leak_customer_pii(
    client, mailoutbox, settings
) -> None:  # type: ignore[no-untyped-def]
    """§41: "customer PII never appears in logs or error pages". Stage
    13's mail_admins handler (config/settings/base.py) emails the admin
    an exception report on any unhandled 500 — sensitive_post_parameters()
    on CheckoutView.post (orders/views.py) must keep the customer's name,
    phone, email, and address out of that report's POST-parameters
    section, not just out of the customer-facing response.
    """
    settings.ADMINS = [("Test Admin", "admin@example.com")]
    variant = _variant_with_stock(5)
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    client.raise_request_exception = False

    with patch("orders.views.create_order", side_effect=RuntimeError("boom")):
        response = client.post(CHECKOUT_URL, _checkout_post_data())

    assert response.status_code == 500
    assert len(mailoutbox) == 1
    body = mailoutbox[0].body
    assert "Ayesha Khan" not in body
    assert "03001234567" not in body
    assert "ayesha@example.com" not in body
    assert "House 1, Street 2" not in body
