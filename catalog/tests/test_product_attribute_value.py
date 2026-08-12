from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from catalog.factories import AttributeValueFactory, ProductFactory
from catalog.models import ProductAttributeValue


@pytest.mark.django_db
def test_product_attribute_value_created() -> None:
    product = ProductFactory()
    value = AttributeValueFactory(value="Unisex")
    pav = ProductAttributeValue.objects.create(product=product, value=value)
    assert pav.product_id == product.pk


@pytest.mark.django_db
def test_duplicate_product_attribute_value_raises_integrity_error() -> None:
    product = ProductFactory()
    value = AttributeValueFactory(value="Unisex")
    ProductAttributeValue.objects.create(product=product, value=value)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductAttributeValue.objects.create(product=product, value=value)
