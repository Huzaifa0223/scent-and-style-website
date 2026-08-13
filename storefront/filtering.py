"""Storefront listing filters (§16-17) — one place that knows how to turn
query-string params into a filtered ``Product`` queryset, reused for both
the main result set and every facet's own count.

Every variant-touching filter (price, attribute values) is an ``Exists()``
subquery, never a ``.filter(variants__...)`` join — the roadmap's own trap
note: joining a to-many relation fans a product row out once per matching
variant, corrupting both the result set's distinctness and the paginator's
count. ``category``/``brand`` are plain FK filters on ``Product`` itself,
no fan-out risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TypedDict, cast

from django.db.models import Count, Exists, OuterRef, Q
from django.http import QueryDict

from catalog.models import (
    AttributeDefinition,
    AttributeValue,
    ProductQuerySet,
    ProductVariant,
    VariantAttributeValue,
)


class BrandFacetRow(TypedDict):
    brand__slug: str
    brand__name: str
    count: int


class AttributeFacetRow(TypedDict):
    value: AttributeValue
    count: int


@dataclass(frozen=True)
class ListingFilters:
    """Parsed, validated filter state for one listing request. Every field
    round-trips through the query string, which is what makes filter state
    survive a reload or the back button (gate 2) for free — there is no
    server-side session state to lose."""

    category_slug: str = ""
    brand_slug: str = ""
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    # {AttributeDefinition.slug: [AttributeValue.slug, ...]} — AND across
    # keys (different attributes), OR within a key's list (same attribute).
    attribute_groups: dict[str, list[str]] = field(default_factory=dict)


def _parse_decimal(raw: str) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def filters_from_query_params(params: QueryDict, *, category_slug: str = "") -> ListingFilters:
    """``category_slug`` is passed separately (from the URL kwarg on
    ``/category/<slug>/``) rather than read from ``params`` — the category
    listing page's category isn't a togglable facet, it's the page."""
    attribute_groups: dict[str, list[str]] = {}
    for definition_slug in AttributeDefinition.objects.filter(is_filterable=True).values_list(
        "slug", flat=True
    ):
        values = params.getlist(definition_slug)
        if values:
            attribute_groups[definition_slug] = values

    return ListingFilters(
        category_slug=category_slug or params.get("category", "").strip(),
        brand_slug=params.get("brand", "").strip(),
        price_min=_parse_decimal(params.get("price_min", "").strip()),
        price_max=_parse_decimal(params.get("price_max", "").strip()),
        attribute_groups=attribute_groups,
    )


def apply_filters(
    queryset: ProductQuerySet, filters: ListingFilters, *, exclude: str | None = None
) -> ProductQuerySet:
    """Applies every active filter except ``exclude``. Passing
    ``exclude="brand"`` (for example) gives the queryset a facet-count
    function should count *brand* options against — every other active
    filter still applies, only brand itself is left open — which is what
    "counts reflect the other active filters, not the unfiltered catalog"
    (§16-17) actually means.
    """
    if filters.category_slug and exclude != "category":
        queryset = queryset.filter(
            Q(category__slug=filters.category_slug) | Q(subcategory__slug=filters.category_slug)
        )

    if filters.brand_slug and exclude != "brand":
        queryset = queryset.filter(brand__slug=filters.brand_slug)

    if (filters.price_min is not None or filters.price_max is not None) and exclude != "price":
        price_match = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
        if filters.price_min is not None:
            price_match = price_match.filter(price__gte=filters.price_min)
        if filters.price_max is not None:
            price_match = price_match.filter(price__lte=filters.price_max)
        queryset = queryset.filter(Exists(price_match))

    for attribute_slug, value_slugs in filters.attribute_groups.items():
        if exclude == attribute_slug:
            continue
        attribute_match = VariantAttributeValue.objects.filter(
            variant__product=OuterRef("pk"), value__slug__in=value_slugs
        )
        queryset = queryset.filter(Exists(attribute_match))

    return queryset


def brand_facet_counts(
    base_queryset: ProductQuerySet, filters: ListingFilters
) -> list[BrandFacetRow]:
    """One query, safe because ``brand`` is a direct FK on ``Product`` —
    grouping by it can't fan out the way a to-many relation would."""
    queryset = apply_filters(base_queryset, filters, exclude="brand")
    rows = (
        queryset.exclude(brand__isnull=True)
        .values("brand__slug", "brand__name")
        .annotate(count=Count("id", distinct=True))
        .order_by("brand__name")
    )
    return cast(list[BrandFacetRow], list(rows))


def attribute_facet_counts(
    base_queryset: ProductQuerySet, filters: ListingFilters, definition: AttributeDefinition
) -> list[AttributeFacetRow]:
    """One ``Exists()``-filtered ``.count()`` per candidate value — O(values
    for this attribute), not O(products in the catalog), so this stays flat
    as the product fixture count grows (gate 5) even though it isn't a
    single query. The number of values a merchant defines for one
    attribute (Color, Size, ...) doesn't grow with catalog size."""
    queryset = apply_filters(base_queryset, filters, exclude=definition.slug)
    results: list[AttributeFacetRow] = []
    for value in definition.values.all():
        value_match = VariantAttributeValue.objects.filter(
            variant__product=OuterRef("pk"), value=value
        )
        count = queryset.filter(Exists(value_match)).count()
        if count:
            results.append({"value": value, "count": count})
    return results
