from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from catalog import services
from catalog.factories import CategoryFactory
from catalog.models import Product, ProductVariant


@pytest.mark.django_db
def test_create_product_creates_product_and_default_variant_together() -> None:
    category = CategoryFactory()
    product = services.create_product(
        name="Afnan 9PM", category=category, default_variant_price=Decimal("25.00")
    )
    assert product.pk is not None
    variant = product.variants.get()
    assert variant.is_default is True
    assert variant.price == Decimal("25.00")
    assert variant.sku == "AFNAN-9PM-DEFAULT"


@pytest.mark.django_db
def test_create_product_sku_collision_gets_a_suffix() -> None:
    """The second product's slug is itself disambiguated to "afnan-9pm-2"
    (Product's own slug collision handling), so its default SKU is derived
    from that already-unique slug — no separate SKU-level suffix needed."""
    category = CategoryFactory()
    first = services.create_product(name="Afnan 9PM", category=category)
    second = services.create_product(name="Afnan 9PM", category=category)
    assert first.variants.get().sku == "AFNAN-9PM-DEFAULT"
    assert second.slug == "afnan-9pm-2"
    assert second.variants.get().sku == "AFNAN-9PM-2-DEFAULT"


@pytest.mark.django_db
def test_create_product_accepts_an_explicit_sku() -> None:
    category = CategoryFactory()
    product = services.create_product(
        name="Afnan 9PM", category=category, default_variant_sku="EDP-9PM-100"
    )
    assert product.variants.get().sku == "EDP-9PM-100"


@pytest.mark.django_db
def test_create_product_is_atomic_a_failure_leaves_no_orphan_product() -> None:
    """If product creation itself fails (invalid data), nothing should be
    left behind — the whole function is one @transaction.atomic unit."""
    before = Product.objects.count()
    with pytest.raises(IntegrityError), transaction.atomic():
        services.create_product(name="No Category")  # category is required, no default
    assert Product.objects.count() == before


@pytest.mark.django_db(transaction=True)
def test_bare_product_create_without_a_variant_fails_at_commit() -> None:
    """The deferred constraint trigger is the backstop for callers that
    bypass catalog.services.create_product. Needs a real commit to observe
    (transaction=True), since a DEFERRABLE INITIALLY DEFERRED constraint is
    only checked at COMMIT — the default django_db transaction wrapping,
    which rolls back instead of committing, would never trigger it."""
    category = CategoryFactory()
    with pytest.raises(IntegrityError):
        Product.objects.create(name="Orphan Product", category=category)


@pytest.mark.django_db(transaction=True)
def test_deleting_the_last_variant_of_a_product_fails_at_commit() -> None:
    category = CategoryFactory()
    product = services.create_product(name="Solo Product", category=category)
    variant = product.variants.get()
    with pytest.raises(IntegrityError):
        variant.delete()


@pytest.mark.django_db(transaction=True)
def test_deleting_the_product_itself_cascades_its_variant_without_error() -> None:
    """The variant-delete trigger must not fire when the product row is
    also gone by commit time (a cascade delete), only when the product
    survives but ends up with zero variants."""
    category = CategoryFactory()
    product = services.create_product(name="Cascade Product", category=category)
    product_id = product.pk
    product.delete()
    assert not Product.objects.filter(pk=product_id).exists()
    assert not ProductVariant.objects.filter(product_id=product_id).exists()
