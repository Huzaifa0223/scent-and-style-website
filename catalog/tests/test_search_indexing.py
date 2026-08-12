"""catalog.search_indexing: compute_search_text()'s field coverage, and the
signal wiring (catalog/signals.py) that keeps Product.search_text current
without a manual command — Stage 5 gate 2 lives here.
"""

from __future__ import annotations

import pytest

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    BrandFactory,
    ProductFactory,
    ProductVariantFactory,
    SubcategoryFactory,
    TagFactory,
    VariantAttributeValueFactory,
)
from catalog.models import ProductAttributeValue
from catalog.search_indexing import compute_search_text, rebuild_search_text


@pytest.mark.django_db
def test_compute_search_text_includes_name_and_category() -> None:
    product = ProductFactory(name="Afnan 9PM Eau de Parfum")

    text = compute_search_text(product)

    assert "afnan 9pm eau de parfum" in text
    assert product.category.name.lower() in text


@pytest.mark.django_db
def test_compute_search_text_includes_brand_and_subcategory() -> None:
    brand = BrandFactory(name="Afnan")
    subcategory = SubcategoryFactory(name="Fragrances")
    product = ProductFactory(brand=brand, subcategory=subcategory, category=subcategory.parent)

    text = compute_search_text(product)

    assert "afnan" in text
    assert "fragrances" in text


@pytest.mark.django_db
def test_compute_search_text_includes_all_variant_skus() -> None:
    product = ProductFactory()
    product.variants.update(sku="EDP-9PM-100")
    ProductVariantFactory(product=product, sku="EDP-9PM-50")

    text = compute_search_text(product)

    assert "edp-9pm-100" in text
    assert "edp-9pm-50" in text


@pytest.mark.django_db
def test_compute_search_text_includes_tags() -> None:
    product = ProductFactory()
    product.tags.add(TagFactory(name="Bestseller"))

    text = compute_search_text(product)

    assert "bestseller" in text


@pytest.mark.django_db
def test_compute_search_text_includes_filterable_product_and_variant_attribute_values() -> None:
    product = ProductFactory()
    filterable = AttributeDefinitionFactory(is_filterable=True)
    product_value = AttributeValueFactory(definition=filterable, value="Unisex")
    ProductAttributeValue.objects.create(product=product, value=product_value)
    variant_value = AttributeValueFactory(definition=filterable, value="Red")
    VariantAttributeValueFactory(variant=product.variants.get(), value=variant_value)

    text = compute_search_text(product)

    assert "unisex" in text
    assert "red" in text


@pytest.mark.django_db
def test_compute_search_text_excludes_non_filterable_attribute_values() -> None:
    product = ProductFactory()
    not_filterable = AttributeDefinitionFactory(is_filterable=False)
    internal_value = AttributeValueFactory(definition=not_filterable, value="InternalOnlyCode")
    ProductAttributeValue.objects.create(product=product, value=internal_value)

    text = compute_search_text(product)

    assert "internalonlycode" not in text


@pytest.mark.django_db
def test_rebuild_search_text_is_a_no_op_when_the_value_has_not_changed() -> None:
    # ProductFactory already triggers the post_save signal, so search_text
    # is populated by the time the test gets control back.
    product = ProductFactory(name="Stable Name")
    assert "stable name" in product.search_text

    changed = rebuild_search_text(product)

    assert changed is False


@pytest.mark.django_db
def test_renaming_a_product_updates_search_text_without_a_manual_command() -> None:
    """Stage 5 gate 2."""
    product = ProductFactory(name="Old Name")
    assert "old name" in product.search_text

    product.name = "New Name"
    product.save(update_fields=["name", "updated_at"])
    product.refresh_from_db()

    assert "new name" in product.search_text
    assert "old name" not in product.search_text


@pytest.mark.django_db
def test_adding_a_variant_updates_the_products_search_text() -> None:
    product = ProductFactory()

    ProductVariantFactory(product=product, sku="NEW-SKU-1")
    product.refresh_from_db()

    assert "new-sku-1" in product.search_text


@pytest.mark.django_db
def test_deleting_a_variant_removes_its_sku_from_search_text() -> None:
    product = ProductFactory()
    extra = ProductVariantFactory(product=product, sku="REMOVE-ME-SKU")
    product.refresh_from_db()
    assert "remove-me-sku" in product.search_text

    extra.delete()
    product.refresh_from_db()

    assert "remove-me-sku" not in product.search_text


@pytest.mark.django_db
def test_adding_and_removing_a_tag_updates_search_text() -> None:
    product = ProductFactory()
    tag = TagFactory(name="Trending")

    product.tags.add(tag)
    product.refresh_from_db()
    assert "trending" in product.search_text

    product.tags.remove(tag)
    product.refresh_from_db()
    assert "trending" not in product.search_text


@pytest.mark.django_db
def test_adding_a_variant_attribute_value_updates_search_text() -> None:
    product = ProductFactory()
    filterable = AttributeDefinitionFactory(is_filterable=True)
    value = AttributeValueFactory(definition=filterable, value="Emerald")

    VariantAttributeValueFactory(variant=product.variants.get(), value=value)
    product.refresh_from_db()

    assert "emerald" in product.search_text
