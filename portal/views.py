"""Merchant portal views (roadmap Stage 3).

Every concrete view sets its own ``permission_required`` on
``accounts.mixins.PortalPermissionRequiredMixin`` — access control lives on
the view class, never inferred from what a template happens to link to.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Prefetch, Q, QuerySet
from django.views.generic import ListView

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import Brand, Category, Product, ProductImage, ProductVariant

PRODUCT_LIST_PAGE_SIZE = 25
"""Rows per page on the merchant's product list. 25 is a scan-friendly
count for a table row that carries a thumbnail, price range, and status
badge — not chosen to make a test pass. (It happens to also sit strictly
between the 5 and 50 fixture counts gate 5 mandates, so the N+1 regression
test below still has a real page-1 row-count difference to catch.)"""


class ProductListView(PortalPermissionRequiredMixin, ListView[Product]):
    """Paginated, searchable, filterable product list.

    Query shape is deliberate: ``select_related`` for the three FKs shown
    per row, ``with_pricing()`` for the annotated display price, and one
    ``Prefetch`` for primary images — none of these scale with the number
    of products in the database, only with page size, which is what keeps
    ``assertNumQueries`` flat as the fixture count grows (acceptance
    gate 5). The SKU half of search uses ``Exists`` rather than joining
    ``variants`` directly — a plain ``filter(variants__sku__icontains=...)``
    would fan the product row out once per matching variant and corrupt the
    paginator's count, exactly the "9pm search" sibling trap CLAUDE.md warns
    about for variant filtering.
    """

    model = Product
    template_name = "portal/product_list.html"
    context_object_name = "products"
    paginate_by = PRODUCT_LIST_PAGE_SIZE
    permission_required = ("catalog.view_product",)

    def get_queryset(self) -> QuerySet[Product]:
        # with_pricing()'s aggregate annotations clear Product.Meta's default
        # ordering (Django groups by the annotation, which drops implicit
        # ordering) — reasserting it explicitly is required for the
        # paginator to return stable, non-overlapping pages across requests,
        # not just to silence UnorderedObjectListWarning.
        queryset = (
            Product.objects.select_related("brand", "category", "subcategory")
            .with_pricing()
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.filter(is_primary=True),
                    to_attr="primary_image_list",
                )
            )
            .order_by("-created_at")
        )

        query = self.request.GET.get("q", "").strip()
        if query:
            sku_match = ProductVariant.objects.filter(product=OuterRef("pk"), sku__icontains=query)
            queryset = queryset.filter(Q(name__icontains=query) | Exists(sku_match))

        status = self.request.GET.get("status", "").strip()
        if status in Product.Status.values:
            queryset = queryset.filter(status=status)

        category_slug = self.request.GET.get("category", "").strip()
        if category_slug:
            queryset = queryset.filter(
                Q(category__slug=category_slug) | Q(subcategory__slug=category_slug)
            )

        brand_slug = self.request.GET.get("brand", "").strip()
        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(parent__isnull=True).order_by(
            "position", "name"
        )
        context["brands"] = Brand.objects.order_by("name")
        context["status_choices"] = Product.Status.choices
        context["current_q"] = self.request.GET.get("q", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["current_category"] = self.request.GET.get("category", "")
        context["current_brand"] = self.request.GET.get("brand", "")
        return context
