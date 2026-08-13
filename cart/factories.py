"""factory-boy fixtures for the cart app."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from catalog.factories import ProductVariantFactory

from .models import Cart, CartItem


class CartFactory(DjangoModelFactory):
    class Meta:
        model = Cart

    session_key = factory.Sequence(lambda n: f"session-{n:08d}")


class CartItemFactory(DjangoModelFactory):
    class Meta:
        model = CartItem

    cart = factory.SubFactory(CartFactory)
    variant = factory.SubFactory(ProductVariantFactory)
    quantity = 1
