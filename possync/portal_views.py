"""Portal "POS mapping" pages (Owner only).

Gated on ``possync.manage_pos_mapping``, which only the Owner/superuser
holds (``accounts/permissions.py`` grants Staff the ``catalog`` app only).
Per the portal's own rule the check lives on the view, never on a hidden
link. Nothing here confirms a mapping on its own and nothing writes a
price.
"""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Subquery
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView, View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import ProductVariant
from orders.models import Order, OrderStatusEvent

from . import matching, services
from .config import (
    BULK_CONFIRM_MIN_SCORE,
    BULK_MAX_ROWS,
    CSV_MAX_BYTES,
    MAPPING_PAGE_SIZE,
    PRICE_MISMATCH_PAGE_SIZE,
)
from .models import PosMappingEvent, PosProduct
from .services import MappingError

MANAGE_PERMISSION = ("possync.manage_pos_mapping",)
STATUS_CHOICES = ("unmapped", "mapped", "not_online", "all")
RECENT_EVENTS = 10
EXPORT_COLUMNS = (
    "sku",
    "brand",
    "name",
    "category",
    "price_rs",
    "active",
    "not_online",
    "website_sku",
    "website_product",
    "website_price_rs",
)


def _back(request: HttpRequest) -> HttpResponseRedirect:
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("possync:mapping")


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


class PosMappingView(PortalPermissionRequiredMixin, ListView[PosProduct]):
    model = PosProduct
    template_name = "portal/pos_mapping.html"
    context_object_name = "pos_products"
    paginate_by = MAPPING_PAGE_SIZE
    permission_required = MANAGE_PERMISSION

    def _status(self) -> str:
        value = self.request.GET.get("status", "unmapped")
        return value if value in STATUS_CHOICES else "unmapped"

    def get_queryset(self) -> QuerySet[PosProduct]:
        mapped = ProductVariant.objects.filter(pos_sku=OuterRef("sku"))
        queryset = PosProduct.objects.annotate(is_mapped=Exists(mapped))
        status = self._status()
        if status == "unmapped":
            queryset = queryset.filter(is_mapped=False, not_online=False)
        elif status == "mapped":
            queryset = queryset.filter(is_mapped=True)
        elif status == "not_online":
            queryset = queryset.filter(not_online=True)
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(sku__icontains=query) | Q(name__icontains=query) | Q(brand__icontains=query)
            )
        return queryset.order_by("brand", "name", "sku")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        rows = list(context["page_obj"].object_list) if context.get("page_obj") else []
        # "Tick the suggested rows" is a plain link (?tick=suggested) so the
        # bulk form works without JavaScript and survives a page reload.
        tick = self.request.GET.get("tick", "")

        # Attach the mapped variant / suggestions to each row object so the
        # template stays a plain loop (no per-row queries, no logic in HTML).
        mapped_by_sku = {
            variant.pos_sku: variant
            for variant in ProductVariant.objects.filter(
                pos_sku__in=[row.sku for row in rows]
            ).select_related("product")
        }
        candidates = (
            services.unmapped_candidates()
            if any(not row.is_mapped and not row.not_online for row in rows)
            else []
        )
        for row in rows:
            row.mapped_variant = mapped_by_sku.get(row.sku)
            row.display_name = matching.strip_leading_brand(row.brand, row.name)
            row.looks_not_online = (
                not row.is_mapped
                and not row.not_online
                and services.looks_not_sold_online(row.category)
            )
            row.ticked = tick == "all" or (tick == "suggested" and row.looks_not_online)
            row.suggestions = (
                matching.suggest(
                    pos_brand=row.brand, pos_name=row.name, pos_sku=row.sku, candidates=candidates
                )
                if not row.is_mapped and not row.not_online
                else []
            )

        # Where bulk actions return to: this page, minus the one-shot ?tick=
        # so the rows that remain are not ticked again.
        keep = self.request.GET.copy()
        keep.pop("tick", None)
        next_url = self.request.path + (f"?{keep.urlencode()}" if keep else "")
        state = services.get_state()
        totals = PosProduct.objects.aggregate(
            total=Count("pk"), not_online=Count("pk", filter=Q(not_online=True))
        )
        mapped_count = ProductVariant.objects.filter(pos_sku__isnull=False).count()
        context.update(
            {
                "rows": rows,
                "tick": tick,
                "next_url": next_url,
                "suggested_not_online_count": sum(1 for row in rows if row.looks_not_online),
                "bulk_min_score": BULK_CONFIRM_MIN_SCORE,
                "status": self._status(),
                "current_q": self.request.GET.get("q", ""),
                "state": state,
                "last_result": state.last_result or {},
                "total_products": totals["total"],
                "not_online_count": totals["not_online"],
                "mapped_count": mapped_count,
                "unmapped_count": max(totals["total"] - mapped_count - totals["not_online"], 0),
                "mismatch_count": services.price_mismatches().count(),
                "awaiting_orders_count": services.awaiting_ack_orders().count(),
                "subtract_web_orders": services.subtract_web_orders_enabled(),
                "recent_events": PosMappingEvent.objects.select_related("actor")[:RECENT_EVENTS],
                "orders_since_value": timezone.localtime(state.orders_since).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            }
        )
        return context


class PosCsvUploadView(PortalPermissionRequiredMixin, View):
    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        upload = request.FILES.get("csv_file")
        if upload is None:
            messages.error(request, "Choose a POS product CSV file to upload.")
            return redirect("possync:mapping")
        if upload.size is not None and upload.size > CSV_MAX_BYTES:
            messages.error(
                request, f"That file is larger than {CSV_MAX_BYTES // (1024 * 1024)} MB."
            )
            return redirect("possync:mapping")

        result = services.import_pos_csv(upload.read(), actor=_actor(request))
        if result.rows_ok:
            messages.success(
                request,
                f"POS products imported: {result.created} new, {result.updated} updated"
                + (f", {len(result.errors)} row(s) skipped." if result.errors else "."),
            )
        for error in result.errors[:10]:
            messages.warning(request, error)
        if len(result.errors) > 10:
            messages.warning(request, f"…and {len(result.errors) - 10} more row error(s).")
        if not result.rows_ok and not result.errors:
            messages.warning(request, "The file contained no product rows.")
        return redirect("possync:mapping")


class PosConfirmMappingView(PortalPermissionRequiredMixin, View):
    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        pos_product = get_object_or_404(PosProduct, pk=pk)
        raw_variant = request.POST.get("variant_id", "")
        if not raw_variant.isdigit():
            messages.error(request, "Pick a variant to map to.")
            return _back(request)
        try:
            variant = services.confirm_mapping(
                pos_product=pos_product, variant_id=int(raw_variant), actor=_actor(request)
            )
        except MappingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"{pos_product.sku} mapped to {variant.sku}.")
        return _back(request)


def _id_list(values: list[str]) -> list[int]:
    """Digits-only form values as ints, de-duplicated, capped at
    ``BULK_MAX_ROWS`` — anything else is ignored rather than trusted."""
    seen: dict[int, None] = {}
    for value in values:
        if value.isdigit():
            seen.setdefault(int(value), None)
    return list(seen)[:BULK_MAX_ROWS]


def _report(request: HttpRequest, result: services.BulkResult, done_text: str) -> None:
    if result.done:
        messages.success(request, f"{result.done} {done_text}")
    for error in result.errors[:10]:
        messages.warning(request, error)
    if len(result.errors) > 10:
        messages.warning(request, f"…and {len(result.errors) - 10} more.")


class PosBulkReviewView(PortalPermissionRequiredMixin, View):
    """Preview every very-likely match, and map only the rows the owner ticks.

    GET changes nothing. POST maps exactly the ``pair`` values ticked
    (``<pos id>:<variant id>``) — an untouched form maps nothing."""

    permission_required = MANAGE_PERMISSION

    def get(self, request: HttpRequest) -> HttpResponse:
        found = services.bulk_match_proposals()
        return render(
            request,
            "portal/pos_bulk_review.html",
            {
                "proposals": found.proposals,
                "left_out": found.ambiguous,
                "min_score": BULK_CONFIRM_MIN_SCORE,
                "tick_all": request.GET.get("tick") == "all",
            },
        )

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        pairs: list[tuple[int, int]] = []
        for raw in request.POST.getlist("pair")[:BULK_MAX_ROWS]:
            pos_id, _, variant_id = raw.partition(":")
            if pos_id.isdigit() and variant_id.isdigit():
                pairs.append((int(pos_id), int(variant_id)))
        if not pairs:
            messages.warning(request, "Nothing was ticked, so nothing was mapped.")
            return redirect("possync:bulk_review")
        result = services.confirm_mappings(pairs=pairs, actor=_actor(request))
        _report(request, result, "POS product(s) mapped.")
        return redirect("possync:mapping")


class PosBulkNotOnlineView(PortalPermissionRequiredMixin, View):
    """Mark every ticked POS product as not sold online in one go."""

    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        pos_ids = _id_list(request.POST.getlist("pos_ids"))
        if not pos_ids:
            messages.warning(request, "Tick at least one product first.")
            return _back(request)
        result = services.set_not_online_many(pos_ids=pos_ids, actor=_actor(request))
        _report(request, result, "POS product(s) marked not sold online.")
        return _back(request)


class PosUnmapView(PortalPermissionRequiredMixin, View):
    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        pos_product = get_object_or_404(PosProduct, pk=pk)
        try:
            services.remove_mapping(pos_sku=pos_product.sku, actor=_actor(request))
        except MappingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Mapping for {pos_product.sku} removed.")
        return _back(request)


class PosNotOnlineView(PortalPermissionRequiredMixin, View):
    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        pos_product = get_object_or_404(PosProduct, pk=pk)
        value = request.POST.get("value", "1") == "1"
        try:
            services.set_not_online(pos_product=pos_product, value=value, actor=_actor(request))
        except MappingError as exc:
            messages.error(request, str(exc))
        else:
            state = "not sold online" if value else "sold online again"
            messages.success(request, f"{pos_product.sku} marked {state}.")
        return _back(request)


class PosOrdersSinceView(PortalPermissionRequiredMixin, View):
    """Move the web-order cutoff (see ``PosSyncState.orders_since``)."""

    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        raw = request.POST.get("orders_since", "").strip()
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            messages.error(request, "Enter a valid date and time.")
            return redirect("possync:mapping")
        if timezone.is_naive(moment):
            moment = timezone.make_aware(moment)
        services.set_orders_since(moment=moment, actor=_actor(request))
        messages.success(request, "Web-order cutoff updated.")
        return redirect("possync:mapping")


class PosMappingExportView(PortalPermissionRequiredMixin, View):
    permission_required = MANAGE_PERMISSION

    def get(self, request: HttpRequest) -> HttpResponse:
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="pos-mapping.csv"'
        writer = csv.writer(response)
        writer.writerow(EXPORT_COLUMNS)
        variants = {
            v.pos_sku: v
            for v in ProductVariant.objects.filter(pos_sku__isnull=False).select_related("product")
        }
        for product in PosProduct.objects.order_by("brand", "name", "sku").iterator():
            variant = variants.get(product.sku)
            writer.writerow(
                [
                    services.csv_safe(value)
                    for value in (
                        product.sku,
                        product.brand,
                        product.name,
                        product.category,
                        product.price if product.price is not None else "",
                        "yes" if product.active else "no",
                        "yes" if product.not_online else "no",
                        variant.sku if variant else "",
                        variant.product.name if variant else "",
                        variant.price if variant else "",
                    )
                ]
            )
        return response


class PosPriceMismatchView(PortalPermissionRequiredMixin, ListView[ProductVariant]):
    """Variants whose website price differs from the POS price — to be fixed
    by hand on the product page. Never fixed automatically."""

    model = ProductVariant
    template_name = "portal/pos_price_mismatches.html"
    context_object_name = "variants"
    paginate_by = PRICE_MISMATCH_PAGE_SIZE
    permission_required = MANAGE_PERMISSION

    def get_queryset(self) -> QuerySet[ProductVariant]:
        return services.price_mismatches()


class PosAwaitingOrdersView(PortalPermissionRequiredMixin, ListView[Order]):
    """Web orders the POS has not recorded yet, each with a "mark recorded"
    form. No customer details are shown — only what is needed to decide."""

    model = Order
    template_name = "portal/pos_orders.html"
    context_object_name = "orders"
    permission_required = MANAGE_PERMISSION

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["subtract_web_orders"] = services.subtract_web_orders_enabled()
        return context

    def get_queryset(self) -> QuerySet[Order]:
        latest_confirmation = (
            OrderStatusEvent.objects.filter(order=OuterRef("pk"), to_status=Order.Status.CONFIRMED)
            .order_by("-created_at")
            .values("created_at")[:1]
        )
        return (
            services.awaiting_ack_orders()
            .annotate(confirmed_at=Subquery(latest_confirmation))
            .prefetch_related("items")
            .order_by("confirmed_at", "pk")
        )


class PosMarkRecordedView(PortalPermissionRequiredMixin, View):
    """Owner-only: take one web order out of the awaiting-ack count, with a
    mandatory reason, audited. See ``services.mark_recorded``."""

    permission_required = MANAGE_PERMISSION

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        order = get_object_or_404(Order, pk=pk)
        try:
            services.mark_recorded(
                order=order, reason=request.POST.get("reason", ""), actor=_actor(request)
            )
        except MappingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                f"Order {order.order_number} marked as recorded. Its units stop being "
                "subtracted at the next POS stock snapshot.",
            )
        return redirect("possync:orders")
