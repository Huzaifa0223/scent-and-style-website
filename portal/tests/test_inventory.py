"""Merchant inventory page (Stage 4, requirements §10.5): the table, its
filters, and inline adjustment. Owner-only for now — Staff has no
inventory.* permission until Stage 17 (see portal/inventory_views.py's
module docstring).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.factories import ProductFactory
from catalog.models import Product
from inventory.factories import StockReservationFactory
from inventory.models import InventoryAdjustment


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


@pytest.mark.django_db
def test_inventory_list_shows_on_hand_reserved_and_available(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(name="Reserved Sneaker")
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.sku = "RESERVED-SKU"
    variant.save(update_fields=["stock_quantity", "sku", "updated_at"])
    StockReservationFactory(variant=variant, quantity=4)

    response = client.get("/admin-portal/inventory/")

    assert response.status_code == 200
    assert b"RESERVED-SKU" in response.content
    content = response.content.decode()
    assert ">10<" in content  # on hand
    assert ">4<" in content  # reserved
    assert ">6<" in content  # available


@pytest.mark.django_db
def test_inventory_list_filters_by_low_stock(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    low = ProductFactory(name="Low Stock Item")
    low_variant = low.variants.get()
    low_variant.stock_quantity = 2
    low_variant.low_stock_threshold = 5
    low_variant.save(update_fields=["stock_quantity", "low_stock_threshold", "updated_at"])
    healthy = ProductFactory(name="Healthy Stock Item")
    healthy_variant = healthy.variants.get()
    healthy_variant.stock_quantity = 50
    healthy_variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.get("/admin-portal/inventory/", {"stock": "low"})

    assert b"Low Stock Item" in response.content
    assert b"Healthy Stock Item" not in response.content


@pytest.mark.django_db
def test_inventory_list_filters_by_out_of_stock(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    out = ProductFactory(name="Out Of Stock Item")
    out_variant = out.variants.get()
    out_variant.stock_quantity = 0
    out_variant.save(update_fields=["stock_quantity", "updated_at"])
    healthy = ProductFactory(name="Healthy Stock Item")
    healthy_variant = healthy.variants.get()
    healthy_variant.stock_quantity = 50
    healthy_variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.get("/admin-portal/inventory/", {"stock": "out"})

    assert b"Out Of Stock Item" in response.content
    assert b"Healthy Stock Item" not in response.content


@pytest.mark.django_db
def test_inline_adjustment_sets_stock_and_records_the_actor(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = _login_owner(client, django_user_model)
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.post(
        f"/admin-portal/inventory/{variant.pk}/adjust/",
        {"absolute_quantity": "25", "note": "Recount"},
    )

    assert response.status_code == 302
    variant.refresh_from_db()
    assert variant.stock_quantity == 25
    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.delta == 15
    assert adjustment.reason == InventoryAdjustment.Reason.MANUAL
    assert adjustment.actor == owner
    assert adjustment.note == "Recount"


@pytest.mark.django_db
def test_inline_adjustment_with_a_non_numeric_value_shows_an_error_and_changes_nothing(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.post(
        f"/admin-portal/inventory/{variant.pk}/adjust/",
        {"absolute_quantity": "not-a-number"},
        follow=True,
    )

    assert response.status_code == 200
    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    assert InventoryAdjustment.objects.filter(variant=variant).count() == 0
    assert b"Enter a whole number" in response.content


@pytest.mark.django_db
def test_staff_cannot_view_the_inventory_page(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Owner-only for now — Staff has no inventory.* permission until
    Stage 17 (accounts/permissions.py's _STAFF_PERMISSION_APP_LABELS is
    catalog-only)."""
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)

    response = client.get("/admin-portal/inventory/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_cannot_post_an_adjustment(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])

    response = client.post(
        f"/admin-portal/inventory/{variant.pk}/adjust/", {"absolute_quantity": "0"}
    )

    assert response.status_code == 403
    variant.refresh_from_db()
    assert variant.stock_quantity == 10


@pytest.mark.django_db
def test_inventory_list_query_count_stays_flat_as_fixture_count_grows(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Same technique as the product list's own gate-5 test — flat query
    count as the fixture count grows, proving with_available_quantity()
    is actually being used rather than a per-row Python computation."""
    _login_owner(client, django_user_model)
    list_url = "/admin-portal/inventory/"
    client.get(list_url)  # warm up StoreSettings.load(), session/cache tables

    for _ in range(3):
        product = ProductFactory()
        variant = product.variants.get()
        StockReservationFactory(variant=variant, quantity=1)
        StockReservationFactory(
            variant=variant, quantity=1, expires_at=timezone.now() - timedelta(hours=1)
        )
    with CaptureQueriesContext(connection) as captured_at_3:
        response = client.get(list_url)
    assert response.status_code == 200
    queries_at_3 = len(captured_at_3)

    for _ in range(12):
        product = ProductFactory()
        variant = product.variants.get()
        StockReservationFactory(variant=variant, quantity=1)
        StockReservationFactory(
            variant=variant, quantity=1, expires_at=timezone.now() - timedelta(hours=1)
        )
    assert Product.objects.count() == 15
    with CaptureQueriesContext(connection) as captured_at_15:
        response = client.get(list_url)
    assert response.status_code == 200
    queries_at_15 = len(captured_at_15)

    assert queries_at_15 == queries_at_3, (
        f"query count grew with fixture count: {queries_at_3} at 3 variants, "
        f"{queries_at_15} at 15 — likely an N+1"
    )
