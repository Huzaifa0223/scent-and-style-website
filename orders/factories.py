"""factory-boy fixtures for the orders app."""

from __future__ import annotations

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from catalog.factories import ProductVariantFactory
from customers.factories import CustomerFactory

from .models import Order, OrderItem


class OrderFactory(DjangoModelFactory):
    class Meta:
        model = Order

    order_number = factory.Sequence(lambda n: f"ORD-{10000 + n}-XXX")
    customer = factory.SubFactory(CustomerFactory)
    customer_name = factory.LazyAttribute(lambda o: o.customer.name)
    customer_phone = factory.LazyAttribute(lambda o: o.customer.phone)
    customer_whatsapp_number = factory.LazyAttribute(lambda o: o.customer.phone)
    delivery_address = "123 Test Street"
    delivery_city = "Karachi"
    subtotal = Decimal("100.00")
    delivery_charge = Decimal("0.00")
    total = Decimal("100.00")


class OrderItemFactory(DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    variant = factory.SubFactory(ProductVariantFactory)
    product_name = factory.LazyAttribute(lambda i: i.variant.product.name)
    variant_label = factory.LazyAttribute(lambda i: i.variant.sku)
    sku = factory.LazyAttribute(lambda i: i.variant.sku)
    unit_price = factory.LazyAttribute(lambda i: i.variant.price)
    quantity = 1
    line_total = factory.LazyAttribute(lambda i: i.variant.price)
