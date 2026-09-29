"""Order-verified review submission and publication behavior."""

from __future__ import annotations

import pytest
from django.urls import reverse

from catalog.factories import ProductFactory
from catalog.models import Product
from orders.factories import OrderFactory, OrderItemFactory
from orders.models import Order, ProductReview


@pytest.mark.django_db
def test_delivered_order_customer_can_submit_pending_review(client) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(status=Product.Status.PUBLISHED)
    order = OrderFactory(
        status=Order.Status.DELIVERED,
        customer_phone="+923001234567",
    )
    OrderItemFactory(order=order, variant=product.variants.get())

    response = client.post(
        reverse("storefront:product_review_submit", kwargs={"slug": product.slug}),
        {
            "order_number": order.order_number,
            "mobile_number": "03001234567",
            "rating": "5",
            "title": "Lovely scent",
            "body": "Exactly as described.",
        },
    )

    review = ProductReview.objects.get()
    assert response.status_code == 302
    assert response.url == f"{product.get_absolute_url()}#reviews"
    assert review.product == product
    assert review.order_item.order == order
    assert review.rating == 5
    assert review.is_approved is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "mobile_number", "include_product"),
    [
        (Order.Status.PENDING_CONFIRMATION, "03001234567", True),
        (Order.Status.DELIVERED, "03009999999", True),
        (Order.Status.DELIVERED, "03001234567", False),
    ],
)
def test_unverified_order_cannot_create_review(
    client, status: str, mobile_number: str, include_product: bool
) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(status=Product.Status.PUBLISHED)
    order = OrderFactory(status=status, customer_phone="+923001234567")
    if include_product:
        OrderItemFactory(order=order, variant=product.variants.get())

    client.post(
        reverse("storefront:product_review_submit", kwargs={"slug": product.slug}),
        {
            "order_number": order.order_number,
            "mobile_number": mobile_number,
            "rating": "4",
            "title": "",
            "body": "A review.",
        },
    )

    assert ProductReview.objects.count() == 0


@pytest.mark.django_db
def test_reviews_only_render_after_merchant_approval(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(status=Product.Status.PUBLISHED)
    order = OrderFactory(status=Order.Status.DELIVERED)
    item = OrderItemFactory(order=order, variant=product.variants.get())
    review = ProductReview.objects.create(
        product=product,
        order_item=item,
        rating=5,
        body="Approved review text.",
        is_approved=False,
    )
    owner = django_user_model.objects.create_superuser(
        username="review-owner", email="owner@example.com", password="secret"
    )
    client.force_login(owner)
    response = client.post(
        reverse("portal:review_moderate", kwargs={"pk": review.pk}), {"action": "approve"}
    )

    review.refresh_from_db()
    product_response = client.get(product.get_absolute_url())
    assert response.status_code == 302
    assert review.is_approved is True
    assert b"Approved review text." in product_response.content
