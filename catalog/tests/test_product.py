from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from catalog.factories import CategoryFactory, ProductFactory, ProductVariantFactory
from catalog.models import Product


@pytest.mark.django_db
def test_slug_generated_and_stable_across_renames() -> None:
    product = ProductFactory(name="Afnan 9PM Eau de Parfum")
    original_slug = product.slug
    product.name = "Afnan 9PM Renamed"
    product.save()
    assert product.slug == original_slug


@pytest.mark.django_db
def test_subcategory_must_be_a_child_of_the_selected_category() -> None:
    category = CategoryFactory(name="Fragrances")
    other_top_level = CategoryFactory(name="Skincare")
    unrelated_sub = CategoryFactory(name="Moisturisers", parent=other_top_level)
    with pytest.raises(ValidationError) as exc_info:
        ProductFactory(category=category, subcategory=unrelated_sub)
    assert "subcategory" in exc_info.value.message_dict


@pytest.mark.django_db
def test_subcategory_that_is_a_real_child_of_category_is_accepted() -> None:
    category = CategoryFactory(name="Fragrances")
    sub = CategoryFactory(name="Men's Fragrances", parent=category)
    product = ProductFactory(category=category, subcategory=sub)
    assert product.subcategory_id == sub.pk


@pytest.mark.django_db
def test_default_status_is_draft() -> None:
    product = ProductFactory()
    assert product.status == Product.Status.DRAFT


@pytest.mark.django_db
def test_with_pricing_display_price_is_minimum_of_active_variants() -> None:
    """Acceptance gate 5: display_price returns the minimum across active
    variants and ignores inactive ones."""
    product = ProductFactory(default_variant_price=Decimal("20.00"))
    default_variant = product.variants.get()
    default_variant.is_active = False
    default_variant.save(update_fields=["is_active"])
    ProductVariantFactory(product=product, sku="A", price=Decimal("30.00"), is_active=True)
    ProductVariantFactory(product=product, sku="B", price=Decimal("45.00"), is_active=True)
    ProductVariantFactory(product=product, sku="C", price=Decimal("99.00"), is_active=False)

    annotated = Product.objects.with_pricing().get(pk=product.pk)
    assert annotated.display_price == Decimal("30.00")


@pytest.mark.django_db
def test_with_pricing_has_price_range_true_when_prices_differ() -> None:
    product = ProductFactory(default_variant_price=Decimal("20.00"))
    ProductVariantFactory(product=product, sku="A", price=Decimal("30.00"))

    annotated = Product.objects.with_pricing().get(pk=product.pk)
    assert annotated.has_price_range is True


@pytest.mark.django_db
def test_with_pricing_has_price_range_false_when_single_active_price() -> None:
    product = ProductFactory(default_variant_price=Decimal("20.00"))
    # a second variant at the SAME price as the default — still one price point
    ProductVariantFactory(product=product, sku="A", price=Decimal("20.00"))

    annotated = Product.objects.with_pricing().get(pk=product.pk)
    assert annotated.has_price_range is False


@pytest.mark.django_db
def test_with_pricing_display_price_is_none_when_no_active_variants() -> None:
    product = ProductFactory()
    product.variants.update(is_active=False)

    annotated = Product.objects.with_pricing().get(pk=product.pk)
    assert annotated.display_price is None
    assert annotated.has_price_range is False


@pytest.mark.django_db
def test_with_pricing_is_a_single_query(django_assert_num_queries) -> None:
    product = ProductFactory(default_variant_price=Decimal("20.00"))
    ProductVariantFactory(product=product, sku="A", price=Decimal("30.00"))
    with django_assert_num_queries(1):
        list(Product.objects.with_pricing().filter(pk=product.pk))
