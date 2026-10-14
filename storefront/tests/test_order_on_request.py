"""Order on request (D-079): a perfume that is off the shelf can be asked for
on WhatsApp instead of showing a dead "unavailable". Nothing is added to the
cart, reserved or charged; the merchant confirms the day."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse

from cart.models import CartItem
from catalog.factories import ProductFactory
from catalog.models import Product
from inventory.models import StockReservation
from store.models import StoreSettings


def _store(*, whatsapp: str = "0334 1172222", lead_days: int = 1) -> None:
    settings_obj = StoreSettings.load()
    settings_obj.whatsapp_number = whatsapp
    settings_obj.order_lead_days_default = lead_days
    settings_obj.save()


def _product(*, stock: int, order_lead_days: int | None = None) -> Product:
    product = ProductFactory(
        name="Khamrah", default_variant_price=Decimal("8500.00"), status=Product.Status.PUBLISHED
    )
    product.variants.update(stock_quantity=stock, order_lead_days=order_lead_days)
    return product


def _variant_row(client, product: Product) -> dict:  # type: ignore[type-arg,no-untyped-def]
    response = client.get(f"/product/{product.slug}/")
    assert response.status_code == 200
    return response.context["variants_data"][0], response


@pytest.mark.django_db
def test_off_the_shelf_product_gets_a_whatsapp_request_with_the_store_default(client) -> None:  # type: ignore[no-untyped-def]
    _store(lead_days=1)
    product = _product(stock=0)

    row, response = _variant_row(client, product)

    assert row["order_lead_days"] == 1
    parsed = urlparse(row["request_url"])
    # The number is stored the way the merchant says it; the link must carry
    # the country code and no leading zero.
    assert parsed.netloc.split(".")[0] == "wa"
    assert parsed.path == "/923341172222"
    text = parse_qs(parsed.query)["text"][0]
    assert "Khamrah" in text
    assert "1 day" in text
    assert f"/product/{product.slug}/" in text
    assert b"data-order-request" in response.content
    assert b"data-order-on-request" in response.content


@pytest.mark.django_db
def test_a_variant_override_beats_the_store_default(client) -> None:  # type: ignore[no-untyped-def]
    _store(lead_days=1)
    product = _product(stock=0, order_lead_days=7)

    row, _ = _variant_row(client, product)

    assert row["order_lead_days"] == 7
    assert "7 days" in parse_qs(urlparse(row["request_url"]).query)["text"][0]


@pytest.mark.django_db
def test_the_store_default_can_be_changed(client) -> None:  # type: ignore[no-untyped-def]
    _store(lead_days=3)
    product = _product(stock=0)

    row, _ = _variant_row(client, product)

    assert row["order_lead_days"] == 3


@pytest.mark.django_db
def test_in_stock_product_has_no_request_link(client) -> None:  # type: ignore[no-untyped-def]
    _store()
    product = _product(stock=5)

    row, _ = _variant_row(client, product)

    assert row["request_url"] == ""
    assert row["available_quantity"] == 5


@pytest.mark.django_db
def test_without_a_whatsapp_number_the_product_stays_plainly_unavailable(client) -> None:  # type: ignore[no-untyped-def]
    _store(whatsapp="")
    product = _product(stock=0)

    row, _ = _variant_row(client, product)

    assert row["request_url"] == ""


@pytest.mark.django_db
def test_request_does_not_touch_the_cart_or_reserve_stock(client) -> None:  # type: ignore[no-untyped-def]
    _store()
    product = _product(stock=0)

    client.get(f"/product/{product.slug}/")

    assert StockReservation.objects.count() == 0
    variant = product.variants.get()
    response = client.post(reverse("cart:add"), {"variant_id": variant.pk, "quantity": 1})
    assert b"Your cart is empty" in response.content
    assert StockReservation.objects.count() == 0
    assert CartItem.objects.count() == 0


@pytest.mark.django_db
def test_feed_publishes_the_lead_time(client) -> None:  # type: ignore[no-untyped-def]
    _store(lead_days=1)
    _product(stock=0, order_lead_days=7)

    payload = client.get("/api/noor/products.json").json()

    (item,) = payload["items"]
    assert item["inStock"] is False
    assert item["orderLeadDays"] == 7
