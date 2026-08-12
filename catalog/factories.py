"""factory-boy fixtures for the catalog app.

ProductFactory wraps ``catalog.services.create_product`` rather than
``Product.objects.create()`` directly — every factory-made product must have
a real variant from the moment it exists, not one that depends on a
deferred database trigger firing at a commit most tests never make (see
catalog/services.py's module docstring for why).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import factory
from factory.django import DjangoModelFactory

from . import services
from .models import (
    AttributeDefinition,
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Tag,
    VariantAttributeValue,
)


class BrandFactory(DjangoModelFactory):
    class Meta:
        model = Brand

    name = factory.Sequence(lambda n: f"Brand {n}")
    is_published = True


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    is_published = True


class SubcategoryFactory(CategoryFactory):
    parent = factory.SubFactory(CategoryFactory)


class TagFactory(DjangoModelFactory):
    class Meta:
        model = Tag

    name = factory.Sequence(lambda n: f"Tag {n}")


class AttributeDefinitionFactory(DjangoModelFactory):
    class Meta:
        model = AttributeDefinition

    name = factory.Sequence(lambda n: f"Attribute {n}")
    is_variant_option = True
    is_filterable = True


class AttributeValueFactory(DjangoModelFactory):
    class Meta:
        model = AttributeValue

    definition = factory.SubFactory(AttributeDefinitionFactory)
    value = factory.Sequence(lambda n: f"Value {n}")


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    category = factory.SubFactory(CategoryFactory)

    @classmethod
    def _create(cls, model_class: type[Product], *args: Any, **kwargs: Any) -> Product:
        default_variant_price = kwargs.pop("default_variant_price", Decimal("10.00"))
        return services.create_product(default_variant_price=default_variant_price, **kwargs)


class ProductVariantFactory(DjangoModelFactory):
    """An *additional* variant on a product that already has one (from
    ProductFactory) — never used to create the very first variant of a
    product, that's what ProductFactory/create_product already do."""

    class Meta:
        model = ProductVariant

    product = factory.SubFactory(ProductFactory)
    sku = factory.Sequence(lambda n: f"SKU-{n:06d}")
    price = Decimal("10.00")


class ProductImageFactory(DjangoModelFactory):
    class Meta:
        model = ProductImage

    product = factory.SubFactory(ProductFactory)
    image = factory.django.ImageField(width=800, height=600, color="blue", format="JPEG")


class VariantAttributeValueFactory(DjangoModelFactory):
    class Meta:
        model = VariantAttributeValue

    variant = factory.SubFactory(ProductVariantFactory)
    value = factory.SubFactory(AttributeValueFactory)
