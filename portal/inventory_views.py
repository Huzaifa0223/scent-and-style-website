"""Merchant inventory page (roadmap Stage 4, requirements §10.5): product,
variant, SKU, on-hand, reserved, available, low-stock and out-of-stock
flags, inline adjustment, filters.

Owner-only for now, not Staff — gated on an ``inventory.*`` permission
rather than a ``catalog.*`` one. ``accounts/permissions.py``'s
``_STAFF_PERMISSION_APP_LABELS`` deliberately excludes ``"inventory"``
until Stage 17 extends it (see that module's own docstring: "requirements
§32's fuller orders/inventory/customers scope arrives in roadmap Stage
17"); gating on an inventory permission is what makes that true here
without any special-casing.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.views.generic import ListView, View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import Brand, Category, ProductVariant
from inventory import services

INVENTORY_LIST_PAGE_SIZE = 50
"""Rows per page — a merchant scanning for low-stock/out-of-stock variants
wants more per screen than the 25-row product list; not chosen to make a
test pass."""


class InventoryListView(PortalPermissionRequiredMixin, ListView[ProductVariant]):
    """``with_available_quantity()`` is what keeps this flat under
    ``assertNumQueries`` as the fixture count grows — every column this
    page shows (on-hand, reserved, available, both flags) comes from that
    one annotated queryset, never a per-row Python property."""

    model = ProductVariant
    template_name = "portal/inventory_list.html"
    context_object_name = "variants"
    paginate_by = INVENTORY_LIST_PAGE_SIZE
    permission_required = ("inventory.view_stockreservation",)

    def get_queryset(self) -> QuerySet[ProductVariant]:
        queryset = (
            ProductVariant.objects.select_related("product", "product__category", "product__brand")
            .prefetch_related("variant_attribute_values__value")
            .with_available_quantity()
            .order_by("product__name", "position", "id")
        )

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(sku__icontains=query) | Q(product__name__icontains=query))

        stock_filter = self.request.GET.get("stock", "").strip()
        # is_low_stock/is_in_stock are with_available_quantity()'s own
        # annotations, not real model fields — django-stubs can't see
        # runtime .annotate() names, hence the two targeted ignores below.
        if stock_filter == "low":
            queryset = queryset.filter(is_low_stock=True)  # type: ignore[misc]
        elif stock_filter == "out":
            queryset = queryset.filter(is_in_stock=False)  # type: ignore[misc]

        category_slug = self.request.GET.get("category", "").strip()
        if category_slug:
            queryset = queryset.filter(
                Q(product__category__slug=category_slug)
                | Q(product__subcategory__slug=category_slug)
            )

        brand_slug = self.request.GET.get("brand", "").strip()
        if brand_slug:
            queryset = queryset.filter(product__brand__slug=brand_slug)

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(parent__isnull=True).order_by(
            "position", "name"
        )
        context["brands"] = Brand.objects.order_by("name")
        context["current_q"] = self.request.GET.get("q", "")
        context["current_stock"] = self.request.GET.get("stock", "")
        context["current_category"] = self.request.GET.get("category", "")
        context["current_brand"] = self.request.GET.get("brand", "")
        return context


class InventoryAdjustView(PortalPermissionRequiredMixin, View):
    """POST-only inline stock adjustment. ``inventory.services.adjust()``
    already validates and writes the audit row; this view's only job is
    turning a bad or missing form value into a clean message instead of a
    500, and turning ``ValidationError`` into the same."""

    permission_required = ("inventory.add_inventoryadjustment",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        raw_quantity = request.POST.get("absolute_quantity", "").strip()
        note = request.POST.get("note", "").strip()

        if not raw_quantity.isdigit():
            messages.error(request, "Enter a whole number for the new stock count.")
            return redirect("portal:inventory_list")

        try:
            variant = services.adjust(
                variant_id=pk,
                absolute_quantity=int(raw_quantity),
                actor=cast(User, request.user),
                note=note,
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("portal:inventory_list")

        messages.success(request, f"{variant.sku} stock set to {variant.stock_quantity}.")
        return redirect("portal:inventory_list")
