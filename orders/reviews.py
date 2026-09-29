"""Verified product-review submission rules."""

from __future__ import annotations

from catalog.models import Product
from core.phone import normalize_pk_mobile

from .models import Order, OrderItem, ProductReview


def submit_product_review(
    *,
    product: Product,
    order_number: str,
    mobile_number: str,
    rating: int,
    title: str,
    body: str,
) -> ProductReview | None:
    """Create a pending review only for the matching delivered order line."""
    normalized_mobile = normalize_pk_mobile(mobile_number)
    if normalized_mobile is None:
        return None

    order = Order.objects.filter(
        order_number=order_number.strip().upper(),
        customer_phone=normalized_mobile,
        status=Order.Status.DELIVERED,
    ).first()
    if order is None:
        return None

    order_item = (
        OrderItem.objects.filter(order=order, variant__product=product)
        .exclude(variant__isnull=True)
        .first()
    )
    if order_item is None:
        return None

    review, created = ProductReview.objects.get_or_create(
        order_item=order_item,
        defaults={
            "product": product,
            "rating": rating,
            "title": title.strip(),
            "body": body.strip(),
        },
    )
    return review if created else None
