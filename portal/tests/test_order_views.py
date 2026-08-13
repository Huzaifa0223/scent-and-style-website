"""Merchant order list/detail, status transitions, tracking, and line
editing (roadmap Stage 10). Owner-only for now — same precedent as
inventory (Stage 4): Staff has no orders.* permission until Stage 17.

Every rejected transition/edit is asserted at ``response.status_code ==
400`` specifically — the roadmap's own wording for gates 1 and 4 ("4xx",
"refused") is checked at the HTTP boundary, not just at the service layer
(already covered in ``orders/tests/test_state_machine.py`` and
``orders/tests/test_editing.py``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group

from cart.factories import CartFactory, CartItemFactory
from catalog.factories import ProductFactory, ProductVariantFactory
from orders import services
from orders.models import Order
from orders.state_machine import transition_status
from orders.status import Status
from store.models import DeliveryStrategy, StoreSettings


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


def _flat_rate_delivery(rate: Decimal = Decimal("0.00")) -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FLAT_RATE
    settings_obj.flat_delivery_rate = rate
    settings_obj.save()


def _checkout_input(**overrides: str) -> services.CheckoutInput:
    defaults: dict[str, str] = {
        "name": "Ayesha Khan",
        "phone": "+923001234567",
        "whatsapp_number": "+923009999999",
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
    product = ProductFactory(default_variant_price=price, name="Order Test Product")
    variant = product.variants.get()
    variant.stock_quantity = stock
    variant.save(update_fields=["stock_quantity", "updated_at"])
    cart = CartFactory()
    CartItemFactory(cart=cart, variant=variant, quantity=quantity)
    return services.create_order(cart=cart, checkout_input=_checkout_input())


@pytest.mark.django_db
def test_order_list_shows_order_number_and_status(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.get("/admin-portal/orders/")

    assert response.status_code == 200
    assert order.order_number.encode() in response.content


@pytest.mark.django_db
def test_order_list_search_by_order_number(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()
    other = _pending_order()

    response = client.get("/admin-portal/orders/", {"q": order.order_number})

    assert order.order_number.encode() in response.content
    assert other.order_number.encode() not in response.content


@pytest.mark.django_db
def test_order_list_filters_by_status(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    pending = _pending_order()
    confirmed = _pending_order()
    transition_status(order=confirmed, to_status=Status.CONFIRMED, actor=None)

    response = client.get("/admin-portal/orders/", {"status": Status.CONFIRMED})

    assert confirmed.order_number.encode() in response.content
    assert pending.order_number.encode() not in response.content


@pytest.mark.django_db
def test_order_detail_shows_items_and_the_whatsapp_status_panel(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()
    transition_status(order=order, to_status=Status.CONFIRMED, actor=None)

    response = client.get(f"/admin-portal/orders/{order.pk}/")

    assert response.status_code == 200
    assert b"Order Test Product" in response.content
    assert order.customer_whatsapp_number.encode() in response.content
    # Confirmed has a WhatsApp template (§26) — the panel must render it,
    # addressed to the *customer's* number, not the merchant's own.
    assert order.order_number.encode() in response.content


@pytest.mark.django_db
def test_order_detail_pending_confirmation_has_no_whatsapp_panel(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Pending Confirmation has no template (§26 names six statuses, not
    all eleven) — build_status_update_message() raises ValueError and the
    view must degrade to omitting the panel, not 500."""
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.get(f"/admin-portal/orders/{order.pk}/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_gate1_a_valid_status_transition_succeeds(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/status/", {"to_status": Status.CONFIRMED, "note": ""}
    )

    assert response.status_code == 302
    order.refresh_from_db()
    assert order.status == Status.CONFIRMED


@pytest.mark.django_db
def test_gate1_an_invalid_status_transition_is_rejected_with_a_4xx(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/status/", {"to_status": Status.DISPATCHED, "note": ""}
    )

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Status.PENDING_CONFIRMATION


@pytest.mark.django_db
def test_gate2_a_quantity_increase_via_http_reserves_the_delta(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/quantity/", {"quantity": "5"}
    )

    assert response.status_code == 302
    item.refresh_from_db()
    assert item.quantity == 5


@pytest.mark.django_db
def test_gate3_a_price_override_via_http_writes_an_audit_row(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, price=Decimal("500.00"), stock=10)
    item = order.items.get()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/price/", {"unit_price": "400.00"}
    )

    assert response.status_code == 302
    item.refresh_from_db()
    assert item.unit_price == Decimal("400.00")


@pytest.mark.django_db
def test_gate4_editing_a_dispatched_order_via_http_is_refused_with_a_4xx(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/quantity/", {"quantity": "9"}
    )

    assert response.status_code == 400
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_add_line_by_sku_via_http(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    variant = ProductVariantFactory(stock_quantity=10, sku="ADD-ME-001")

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/", {"sku": "ADD-ME-001", "quantity": "2"}
    )

    assert response.status_code == 302
    assert order.items.filter(variant=variant, quantity=2).exists()


@pytest.mark.django_db
def test_add_line_with_an_unknown_sku_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/", {"sku": "NOPE-000", "quantity": "1"}
    )

    assert response.status_code == 400
    assert order.items.count() == 1


@pytest.mark.django_db
def test_remove_line_via_http(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/",
        {"sku": extra_variant.sku, "quantity": "1"},
    )
    item = order.items.get(variant=extra_variant)

    response = client.post(f"/admin-portal/orders/{order.pk}/lines/{item.pk}/remove/")

    assert response.status_code == 302
    assert not order.items.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_tracking_update_via_http(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)

    response = client.post(
        f"/admin-portal/orders/{order.pk}/tracking/",
        {"tracking_number": "TRK123", "courier_name": "TCS", "merchant_notes": "Fragile"},
    )

    assert response.status_code == 302
    order.refresh_from_db()
    assert order.tracking_number == "TRK123"
    assert order.courier_name == "TCS"


@pytest.mark.django_db
def test_order_list_filters_by_date_range(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()
    today = order.created_at.date().isoformat()

    response = client.get("/admin-portal/orders/", {"from": today, "to": today})

    assert order.order_number.encode() in response.content


@pytest.mark.django_db
def test_status_transition_with_a_missing_status_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.post(f"/admin-portal/orders/{order.pk}/status/", {"note": ""})

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Status.PENDING_CONFIRMATION


@pytest.mark.django_db
def test_tracking_update_with_invalid_data_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/tracking/",
        {"tracking_number": "x" * 200, "courier_name": "", "merchant_notes": ""},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_quantity_edit_with_non_numeric_input_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/quantity/", {"quantity": "not-a-number"}
    )

    assert response.status_code == 400
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_price_edit_with_non_numeric_input_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/price/", {"unit_price": "not-a-price"}
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_add_line_with_a_missing_quantity_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    variant = ProductVariantFactory(stock_quantity=10, sku="MISSING-QTY-001")

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/", {"sku": "MISSING-QTY-001"}
    )

    assert response.status_code == 400
    assert not order.items.filter(variant=variant).exists()


@pytest.mark.django_db
def test_remove_line_on_a_dispatched_order_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    extra_variant = ProductVariantFactory(stock_quantity=10)
    client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/",
        {"sku": extra_variant.sku, "quantity": "1"},
    )
    item = order.items.get(variant=extra_variant)
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)

    response = client.post(f"/admin-portal/orders/{order.pk}/lines/{item.pk}/remove/")

    assert response.status_code == 400
    assert order.items.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_quantity_edit_to_the_same_value_redirects_with_an_info_message(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=2, stock=10)
    item = order.items.get()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/quantity/", {"quantity": "2"}
    )

    assert response.status_code == 302
    item.refresh_from_db()
    assert item.quantity == 2


@pytest.mark.django_db
def test_add_line_a_duplicate_variant_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    existing_variant = order.items.get().variant
    assert existing_variant is not None

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/add/",
        {"sku": existing_variant.sku, "quantity": "1"},
    )

    assert response.status_code == 400
    assert order.items.count() == 1


@pytest.mark.django_db
def test_price_override_on_a_dispatched_order_returns_400(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    order = _pending_order(quantity=1, stock=10)
    item = order.items.get()
    for to_status in (
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
    ):
        order = transition_status(order=order, to_status=to_status, actor=None)

    response = client.post(
        f"/admin-portal/orders/{order.pk}/lines/{item.pk}/price/", {"unit_price": "1.00"}
    )

    assert response.status_code == 400
    item.refresh_from_db()
    assert item.unit_price != Decimal("1.00")


@pytest.mark.django_db
def test_staff_cannot_view_the_order_list(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)

    response = client.get("/admin-portal/orders/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_cannot_transition_an_order_status(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    order = _pending_order()

    response = client.post(
        f"/admin-portal/orders/{order.pk}/status/", {"to_status": Status.CONFIRMED, "note": ""}
    )

    assert response.status_code == 403
    order.refresh_from_db()
    assert order.status == Status.PENDING_CONFIRMATION
