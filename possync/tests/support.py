"""Shared helpers for the possync tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from catalog.factories import BrandFactory, ProductFactory
from catalog.models import Product, ProductVariant
from orders.factories import OrderFactory, OrderItemFactory
from orders.models import Order, OrderStatusEvent

# Fake but long enough (>= 32) to be accepted. Deliberately different from
# noor's test token: the two APIs must not accept each other's secret.
POS_TOKEN = "pos-unit-test-token-" + "p" * 32

PING_URL = "/api/pos/sync/ping/"
STOCK_URL = "/api/pos/sync/stock/"
WEB_ORDERS_URL = "/api/pos/sync/web-orders/"


def ack_url(order_id: int) -> str:
    return f"/api/pos/sync/web-orders/{order_id}/ack/"


def auth(token: str = POS_TOKEN) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def minutes_ago(minutes: int) -> str:
    return (timezone.now() - timedelta(minutes=minutes)).isoformat()


def post_json(client: Any, url: str, payload: Any, **extra: Any) -> Any:
    return client.post(
        url,
        data=payload if isinstance(payload, bytes) else json.dumps(payload),
        content_type="application/json",
        secure=True,
        **{**auth(), **extra},
    )


def snapshot(items: list[dict[str, Any]], *, at: str | None = None) -> dict[str, Any]:
    return {"snapshotAt": at or minutes_ago(1), "items": items}


def item(sku: str, on_hand: int, price: Any = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"sku": sku, "onHand": on_hand}
    if price is not None:
        entry["priceRs"] = price
    return entry


def mapped_variant(
    pos_sku: str | None = "POS-1",
    *,
    stock: int = 10,
    price: str = "1000.00",
    name: str = "Khamrah",
    brand: str | None = None,
    status: str = Product.Status.PUBLISHED,
) -> ProductVariant:
    fields: dict[str, Any] = {}
    if brand:
        fields["brand"] = BrandFactory(name=brand)
    product = ProductFactory(
        name=name, status=status, default_variant_price=Decimal(price), **fields
    )
    variant = product.variants.get()
    ProductVariant.objects.filter(pk=variant.pk).update(pos_sku=pos_sku, stock_quantity=stock)
    variant.refresh_from_db()
    return variant


def web_order(
    variant: ProductVariant,
    quantity: int = 1,
    *,
    status: str = Order.Status.CONFIRMED,
    confirmed_at: datetime | None = None,
    **order_fields: Any,
) -> Order:
    """A web order for ``quantity`` of ``variant``, with the confirmation
    event the sync's cutoff looks at."""
    order = OrderFactory(status=status, **order_fields)
    OrderItemFactory(
        order=order,
        variant=variant,
        quantity=quantity,
        unit_price=variant.price,
        line_total=variant.price * quantity,
        product_name=variant.product.name,
    )
    event = OrderStatusEvent.objects.create(
        order=order, from_status="pending_confirmation", to_status=Order.Status.CONFIRMED
    )
    if confirmed_at is not None:
        OrderStatusEvent.objects.filter(pk=event.pk).update(created_at=confirmed_at)
    return order
