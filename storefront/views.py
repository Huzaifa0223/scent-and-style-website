"""Storefront views (roadmap Stage 6, §16-17). Public — no permission
mixin, unlike everything in ``portal``.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from catalog.models import (
    AttributeDefinition,
    Category,
    Product,
    ProductImage,
    ProductQuerySet,
    ProductVariant,
)
from storefront.filtering import (
    apply_filters,
    attribute_facet_counts,
    brand_facet_counts,
    filters_from_query_params,
)

STOREFRONT_PAGE_SIZE = 24
"""A 4- or 6-column desktop grid divides evenly into 24 with no partial
final row for either layout — not chosen to satisfy a test."""

_SORT_OPTIONS = {
    "newest": ("-created_at",),
    "price_asc": ("display_price",),
    "price_desc": ("-display_price",),
    "featured": ("-is_featured", "-created_at"),
}
DEFAULT_SORT = "newest"


class ProductListView(ListView[Product]):
    """Serves both ``/products/`` (no category constraint) and
    ``/category/<slug>/`` (the category comes from the URL, not the query
    string) — one view, since every other facet behaves identically on
    both pages. See ``storefront/filtering.py`` for why every
    variant-touching filter is an ``Exists()`` subquery, never a join.
    """

    model = Product
    template_name = "storefront/product_list.html"
    context_object_name = "products"
    paginate_by = STOREFRONT_PAGE_SIZE

    def get_queryset(self) -> QuerySet[Product]:
        base: ProductQuerySet = Product.objects.filter(
            status=Product.Status.PUBLISHED
        ).select_related("brand", "category", "subcategory")
        self.filters = filters_from_query_params(
            self.request.GET, category_slug=self.kwargs.get("category_slug", "")
        )
        filtered = apply_filters(base, self.filters)

        sort_key = self.request.GET.get("sort", DEFAULT_SORT)
        order_fields = _SORT_OPTIONS.get(sort_key, _SORT_OPTIONS[DEFAULT_SORT])

        return (
            filtered.with_pricing()
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.filter(is_primary=True),
                    to_attr="primary_image_list",
                ),
                Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
            )
            .order_by(*order_fields, "-created_at")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        base: ProductQuerySet = Product.objects.filter(status=Product.Status.PUBLISHED)
        context["category"] = (
            get_object_or_404(Category, slug=self.kwargs["category_slug"])
            if "category_slug" in self.kwargs
            else None
        )
        context["brand_facets"] = brand_facet_counts(base, self.filters)
        context["attribute_facets"] = [
            {
                "definition": definition,
                "values": [
                    {
                        "value": entry["value"],
                        "count": entry["count"],
                        "is_active": entry["value"].slug
                        in self.filters.attribute_groups.get(definition.slug, []),
                    }
                    for entry in attribute_facet_counts(base, self.filters, definition)
                ],
            }
            for definition in AttributeDefinition.objects.filter(is_filterable=True)
        ]
        context["current_sort"] = self.request.GET.get("sort", DEFAULT_SORT)
        context["current_brand"] = self.filters.brand_slug
        context["current_price_min"] = self.request.GET.get("price_min", "")
        context["current_price_max"] = self.request.GET.get("price_max", "")
        return context


class ProductDetailView(DetailView[Product]):
    """The variant selector (gate 3: price/availability/gallery update
    without a reload) is client-side Alpine, driven off ``variants_json`` —
    a single ``<select>`` over full variant labels ("Red / 50ml") rather
    than a per-attribute button grid, since a button grid only maps
    cleanly to one variant when a product varies along exactly one
    attribute dimension; a product varying along two (colour AND size)
    needs the combination, which a `<select>` sidesteps entirely by
    encoding each variant's full combination as one option.
    """

    model = Product
    template_name = "storefront/product_detail.html"
    context_object_name = "product"
    slug_url_kwarg = "slug"

    def get_queryset(self) -> QuerySet[Product]:
        return (
            Product.objects.filter(status=Product.Status.PUBLISHED)
            .select_related("brand", "category", "subcategory")
            .prefetch_related(
                "images",
                Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
                "variants__variant_attribute_values__value__definition",
            )
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        variants = list(self.object.variants.all())
        default_variant = next(
            (v for v in variants if v.is_default), variants[0] if variants else None
        )

        context["gallery_images"] = [
            {
                "id": image.pk,
                "full": image.full_webp.url,
                "thumb": image.thumb_webp.url,
                "alt": image.alt_text or self.object.name,
            }
            for image in self.object.images.all()
        ]
        context["default_variant"] = default_variant
        context["variant_options"] = [
            {"id": variant.pk, "label": variant.display_label} for variant in variants
        ]
        # A plain Python list, not a pre-serialized JSON string — the
        # template's json_script tag does its own serialization/escaping.
        # available_quantity is with_available_quantity()'s runtime
        # .annotate() field — django-stubs can't see it statically.
        context["variants_data"] = [
            {
                "id": variant.pk,
                "price": str(variant.price),
                "available_quantity": variant.available_quantity,  # type: ignore[attr-defined]
            }
            for variant in variants
        ]
        return context


HOME_SECTION_SIZE = 8
"""Featured and new-arrivals rails both cap at 8 — a 4-column desktop grid
divides evenly with no partial final row, same reasoning as
STOREFRONT_PAGE_SIZE."""


class HomeView(ListView[Product]):
    """Featured products, new arrivals, and category tiles on the home page
    (roadmap Stage 6). The two rails deliberately aren't deduplicated
    against each other — "featured" and "newest" are independent
    curations, and a product can legitimately belong to both."""

    model = Product
    template_name = "storefront/home.html"
    context_object_name = "featured_products"

    @staticmethod
    def _with_primary_image(queryset: ProductQuerySet) -> ProductQuerySet:
        return queryset.with_pricing().prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_image_list",
            )
        )

    def get_queryset(self) -> QuerySet[Product]:
        base: ProductQuerySet = Product.objects.filter(
            status=Product.Status.PUBLISHED, is_featured=True
        )
        return self._with_primary_image(base).order_by("-created_at")[:HOME_SECTION_SIZE]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(
            parent__isnull=True, is_published=True
        ).order_by("position", "name")
        new_arrivals: ProductQuerySet = Product.objects.filter(status=Product.Status.PUBLISHED)
        context["new_arrivals"] = self._with_primary_image(new_arrivals).order_by("-created_at")[
            :HOME_SECTION_SIZE
        ]
        return context
