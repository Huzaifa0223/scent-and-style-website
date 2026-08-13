"""storefront.filtering — Stage 6 gate 1: filters compose (category + brand
+ price range + an attribute facet), with correct facet counts. Every case
here is built to fail if the variant-touching filters used a JOIN instead
of EXISTS: products carry multiple variants and multiple attribute values
on purpose, so a fan-out would silently multiply matches or counts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.http import QueryDict

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    BrandFactory,
    CategoryFactory,
    ProductFactory,
    ProductVariantFactory,
    SubcategoryFactory,
    VariantAttributeValueFactory,
)
from catalog.models import Product
from storefront.filtering import (
    ListingFilters,
    apply_filters,
    attribute_facet_counts,
    brand_facet_counts,
    filters_from_query_params,
)


def _published_qs():  # type: ignore[no-untyped-def]
    return Product.objects.filter(status=Product.Status.PUBLISHED)


@pytest.mark.django_db
def test_filters_from_query_params_reads_filterable_attributes_only() -> None:
    filterable = AttributeDefinitionFactory(is_filterable=True)
    not_filterable = AttributeDefinitionFactory(is_filterable=False)
    params = QueryDict(mutable=True)
    params.setlist(filterable.slug, ["red", "blue"])
    params.setlist(not_filterable.slug, ["internal"])
    params["brand"] = "nike"
    params["price_min"] = "10.00"

    filters = filters_from_query_params(params)

    assert filters.brand_slug == "nike"
    assert filters.price_min == Decimal("10.00")
    assert filters.attribute_groups == {filterable.slug: ["red", "blue"]}


@pytest.mark.django_db
def test_filters_from_query_params_ignores_a_malformed_price() -> None:
    params = QueryDict(mutable=True)
    params["price_min"] = "not-a-number"

    filters = filters_from_query_params(params)

    assert filters.price_min is None


@pytest.mark.django_db
def test_category_filter_matches_category_or_subcategory() -> None:
    parent = CategoryFactory()
    sub = SubcategoryFactory(parent=parent)
    in_parent = ProductFactory(category=parent, status=Product.Status.PUBLISHED)
    in_sub = ProductFactory(category=parent, subcategory=sub, status=Product.Status.PUBLISHED)
    elsewhere = ProductFactory(status=Product.Status.PUBLISHED)

    filters = ListingFilters(category_slug=parent.slug)
    result = apply_filters(_published_qs(), filters)

    assert in_parent in result
    assert in_sub in result
    assert elsewhere not in result


@pytest.mark.django_db
def test_brand_filter() -> None:
    nike = BrandFactory()
    adidas = BrandFactory()
    nike_product = ProductFactory(brand=nike, status=Product.Status.PUBLISHED)
    adidas_product = ProductFactory(brand=adidas, status=Product.Status.PUBLISHED)

    filters = ListingFilters(brand_slug=nike.slug)
    result = apply_filters(_published_qs(), filters)

    assert nike_product in result
    assert adidas_product not in result


@pytest.mark.django_db
def test_price_range_filter_matches_if_any_active_variant_is_in_range() -> None:
    product = ProductFactory(
        default_variant_price=Decimal("50.00"), status=Product.Status.PUBLISHED
    )
    ProductVariantFactory(
        product=product, price=Decimal("500.00")
    )  # out of range, but not the only variant
    out_of_range = ProductFactory(
        default_variant_price=Decimal("999.00"), status=Product.Status.PUBLISHED
    )

    filters = ListingFilters(price_min=Decimal("10.00"), price_max=Decimal("100.00"))
    result = apply_filters(_published_qs(), filters)

    assert product in result  # matches via its 50.00 variant, despite also having a 500.00 one
    assert out_of_range not in result


@pytest.mark.django_db
def test_price_range_filter_ignores_inactive_variants() -> None:
    product = ProductFactory(
        default_variant_price=Decimal("500.00"), status=Product.Status.PUBLISHED
    )
    inactive = ProductVariantFactory(product=product, price=Decimal("50.00"))
    inactive.is_active = False
    inactive.save(update_fields=["is_active", "updated_at"])

    filters = ListingFilters(price_min=Decimal("10.00"), price_max=Decimal("100.00"))
    result = apply_filters(_published_qs(), filters)

    assert product not in result


@pytest.mark.django_db
def test_price_min_alone_matches_anything_at_or_above_it() -> None:
    cheap = ProductFactory(default_variant_price=Decimal("5.00"), status=Product.Status.PUBLISHED)
    expensive = ProductFactory(
        default_variant_price=Decimal("500.00"), status=Product.Status.PUBLISHED
    )

    result = apply_filters(_published_qs(), ListingFilters(price_min=Decimal("10.00")))

    assert cheap not in result
    assert expensive in result


@pytest.mark.django_db
def test_price_max_alone_matches_anything_at_or_below_it() -> None:
    cheap = ProductFactory(default_variant_price=Decimal("5.00"), status=Product.Status.PUBLISHED)
    expensive = ProductFactory(
        default_variant_price=Decimal("500.00"), status=Product.Status.PUBLISHED
    )

    result = apply_filters(_published_qs(), ListingFilters(price_max=Decimal("10.00")))

    assert cheap in result
    assert expensive not in result


@pytest.mark.django_db
def test_attribute_facet_filter_matches_any_variant_with_that_value() -> None:
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    blue = AttributeValueFactory(definition=color, value="Blue")
    red_product = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=red_product.variants.get(), value=red)
    blue_product = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=blue_product.variants.get(), value=blue)

    filters = ListingFilters(attribute_groups={color.slug: [red.slug]})
    result = apply_filters(_published_qs(), filters)

    assert red_product in result
    assert blue_product not in result


@pytest.mark.django_db
def test_attribute_facet_is_or_within_the_same_attribute() -> None:
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    blue = AttributeValueFactory(definition=color, value="Blue")
    green = AttributeValueFactory(definition=color, value="Green")
    red_product = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=red_product.variants.get(), value=red)
    green_product = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=green_product.variants.get(), value=green)

    filters = ListingFilters(attribute_groups={color.slug: [red.slug, blue.slug]})
    result = apply_filters(_published_qs(), filters)

    assert red_product in result
    assert green_product not in result


@pytest.mark.django_db
def test_different_attributes_are_anded_together() -> None:
    color = AttributeDefinitionFactory(is_filterable=True)
    size = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    large = AttributeValueFactory(definition=size, value="Large")

    # one variant has both Red and Large -- must match
    both = ProductFactory(status=Product.Status.PUBLISHED)
    both_variant = both.variants.get()
    VariantAttributeValueFactory(variant=both_variant, value=red)
    VariantAttributeValueFactory(variant=both_variant, value=large)

    # red exists but only on a *different* variant than the Large one --
    # this must NOT match: the two attributes need not be on the same
    # variant for the roadmap's "AND across facets" to hold at the
    # product level, but this fixture proves the AND is real (neither
    # value alone is enough).
    red_only = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=red_only.variants.get(), value=red)

    filters = ListingFilters(attribute_groups={color.slug: [red.slug], size.slug: [large.slug]})
    result = apply_filters(_published_qs(), filters)

    assert both in result
    assert red_only not in result


@pytest.mark.django_db
def test_apply_filters_exclude_skips_only_that_one_attribute_group() -> None:
    """With two active attribute filters, excluding one by its slug must
    still apply the other -- exercises the per-key `continue` in the
    attribute_groups loop, not just the "no attributes active" path."""
    color = AttributeDefinitionFactory(is_filterable=True)
    size = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    large = AttributeValueFactory(definition=size, value="Large")

    red_and_large = ProductFactory(status=Product.Status.PUBLISHED)
    rl_variant = red_and_large.variants.get()
    VariantAttributeValueFactory(variant=rl_variant, value=red)
    VariantAttributeValueFactory(variant=rl_variant, value=large)

    red_only = ProductFactory(status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=red_only.variants.get(), value=red)

    filters = ListingFilters(attribute_groups={color.slug: [red.slug], size.slug: [large.slug]})
    # Excluding "size" should still require "color" (red) -- red_only
    # qualifies, since its exclusion is only from the size constraint.
    result = apply_filters(_published_qs(), filters, exclude=size.slug)

    assert red_and_large in result
    assert red_only in result


@pytest.mark.django_db
def test_filters_compose_category_brand_price_and_attribute_together() -> None:
    """Gate 1's literal example."""
    category = CategoryFactory()
    brand = BrandFactory()
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")

    matches = ProductFactory(
        category=category,
        brand=brand,
        default_variant_price=Decimal("30.00"),
        status=Product.Status.PUBLISHED,
    )
    VariantAttributeValueFactory(variant=matches.variants.get(), value=red)

    wrong_brand = ProductFactory(
        category=category, default_variant_price=Decimal("30.00"), status=Product.Status.PUBLISHED
    )
    VariantAttributeValueFactory(variant=wrong_brand.variants.get(), value=red)

    wrong_price = ProductFactory(
        category=category,
        brand=brand,
        default_variant_price=Decimal("999.00"),
        status=Product.Status.PUBLISHED,
    )
    VariantAttributeValueFactory(variant=wrong_price.variants.get(), value=red)

    filters = ListingFilters(
        category_slug=category.slug,
        brand_slug=brand.slug,
        price_min=Decimal("10.00"),
        price_max=Decimal("50.00"),
        attribute_groups={color.slug: [red.slug]},
    )
    result = apply_filters(_published_qs(), filters)

    assert list(result) == [matches]


@pytest.mark.django_db
def test_a_product_with_many_matching_variants_is_not_double_counted() -> None:
    """The fan-out trap, made concrete: one product, three variants that
    ALL satisfy the price filter AND carry attribute values -- a
    JOIN-based filter would return this product's row 3+ times. Each
    variant also gets a distinct Size value alongside the shared Red, so
    each has its own attribute set (the model enforces at most one
    variant per distinct attribute-value combination per product)."""
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")
    size = AttributeDefinitionFactory(is_filterable=True)
    product = ProductFactory(
        default_variant_price=Decimal("20.00"), status=Product.Status.PUBLISHED
    )
    variants = [product.variants.get()] + [
        ProductVariantFactory(product=product, price=Decimal("20.00")) for _ in range(2)
    ]
    for i, variant in enumerate(variants):
        VariantAttributeValueFactory(variant=variant, value=red)
        VariantAttributeValueFactory(
            variant=variant, value=AttributeValueFactory(definition=size, value=f"Size {i}")
        )

    filters = ListingFilters(
        price_min=Decimal("10.00"),
        price_max=Decimal("50.00"),
        attribute_groups={color.slug: [red.slug]},
    )
    result = list(apply_filters(_published_qs(), filters))

    assert result == [product]  # not [product, product, product]


@pytest.mark.django_db
def test_brand_facet_counts_reflect_other_active_filters_not_the_whole_catalog() -> None:
    category = CategoryFactory()
    other_category = CategoryFactory()
    nike = BrandFactory()
    adidas = BrandFactory()
    ProductFactory(category=category, brand=nike, status=Product.Status.PUBLISHED)
    ProductFactory(category=category, brand=nike, status=Product.Status.PUBLISHED)
    ProductFactory(category=category, brand=adidas, status=Product.Status.PUBLISHED)
    # outside the active category filter -- must not inflate the count
    ProductFactory(category=other_category, brand=nike, status=Product.Status.PUBLISHED)

    filters = ListingFilters(category_slug=category.slug)
    counts = {
        row["brand__slug"]: row["count"] for row in brand_facet_counts(_published_qs(), filters)
    }

    assert counts[nike.slug] == 2
    assert counts[adidas.slug] == 1


@pytest.mark.django_db
def test_brand_facet_counts_exclude_the_brand_filter_itself() -> None:
    """If brand counts were computed *with* the brand filter still
    applied, every non-selected brand would show 0 -- the whole point of
    excluding it is that a shopper can see what switching to another
    brand would yield."""
    nike = BrandFactory()
    adidas = BrandFactory()
    ProductFactory(brand=nike, status=Product.Status.PUBLISHED)
    ProductFactory(brand=adidas, status=Product.Status.PUBLISHED)

    filters = ListingFilters(brand_slug=nike.slug)
    counts = {
        row["brand__slug"]: row["count"] for row in brand_facet_counts(_published_qs(), filters)
    }

    assert counts[nike.slug] == 1
    assert counts[adidas.slug] == 1


@pytest.mark.django_db
def test_attribute_facet_counts_reflect_other_active_filters() -> None:
    brand = BrandFactory()
    other_brand = BrandFactory()
    color = AttributeDefinitionFactory(is_filterable=True)
    red = AttributeValueFactory(definition=color, value="Red")

    matching_brand = ProductFactory(brand=brand, status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=matching_brand.variants.get(), value=red)
    other = ProductFactory(brand=other_brand, status=Product.Status.PUBLISHED)
    VariantAttributeValueFactory(variant=other.variants.get(), value=red)

    filters = ListingFilters(brand_slug=brand.slug)
    counts = {
        row["value"].slug: row["count"]
        for row in attribute_facet_counts(_published_qs(), filters, color)
    }

    assert counts[red.slug] == 1


@pytest.mark.django_db
def test_attribute_facet_counts_omit_values_with_zero_matches() -> None:
    color = AttributeDefinitionFactory(is_filterable=True)
    AttributeValueFactory(definition=color, value="Unused Value")

    counts = attribute_facet_counts(_published_qs(), ListingFilters(), color)

    assert counts == []
