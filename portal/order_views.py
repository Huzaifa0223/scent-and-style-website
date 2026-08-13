"""Merchant order list, detail, status transitions, tracking, and line
editing (roadmap Stage 10, requirements §23).

Owner-only for now, not Staff — same precedent as the Stage 4 inventory
page (``portal/inventory_views.py``): gated on ``orders.*`` permissions,
and ``accounts/permissions.py``'s ``_STAFF_PERMISSION_APP_LABELS``
deliberately excludes ``"orders"`` until Stage 17 extends it.

Every action view that can be rejected by a business rule (an invalid
status transition, an edit on a non-editable order, insufficient stock)
re-renders the order detail page with the error **and a 400 status
code**, rather than a 302 redirect carrying a flash message — roadmap
Stage 10's gates are explicit that a disallowed transition and a blocked
edit are each rejected "with a 4xx", and a redirect is a 2xx-via-302, not
a 4xx, at the HTTP layer a test client actually observes.
"""

from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, View

from accounts.mixins import PortalPermissionRequiredMixin
from inventory.services import InsufficientStockError
from notifications.whatsapp.channel import WhatsAppLinkChannel
from notifications.whatsapp.message_builder import build_status_update_message
from orders import editing
from orders.models import Order, OrderItem
from orders.state_machine import InvalidStatusTransitionError, transition_status
from orders.status import ALLOWED_TRANSITIONS, EDITABLE_STATUSES

from .order_forms import (
    OrderLineAddForm,
    OrderLinePriceForm,
    OrderLineQuantityForm,
    OrderStatusTransitionForm,
    OrderTrackingForm,
)

ORDER_LIST_PAGE_SIZE = 25

# The three ways a line edit can be rejected by a business rule rather
# than a form-validation error — every line-editing view catches the same
# set, so it's named once instead of repeated per except clause.
_LINE_EDIT_ERRORS = (editing.OrderNotEditableError, editing.LineEditError, InsufficientStockError)


class OrderListView(PortalPermissionRequiredMixin, ListView[Order]):
    """Filter by status, date range, and free-text search on order number
    or phone (§23's own list of required filters)."""

    model = Order
    template_name = "portal/order_list.html"
    context_object_name = "orders"
    paginate_by = ORDER_LIST_PAGE_SIZE
    permission_required = ("orders.view_order",)

    def get_queryset(self) -> QuerySet[Order]:
        queryset = Order.objects.select_related("customer").order_by("-created_at")

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(order_number__icontains=query) | Q(customer_phone__icontains=query)
            )

        status = self.request.GET.get("status", "").strip()
        if status in Order.Status.values:
            queryset = queryset.filter(status=status)

        date_from = self.request.GET.get("from", "").strip()
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.GET.get("to", "").strip()
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["status_choices"] = Order.Status.choices
        context["current_q"] = self.request.GET.get("q", "")
        context["current_status"] = self.request.GET.get("status", "")
        context["current_from"] = self.request.GET.get("from", "")
        context["current_to"] = self.request.GET.get("to", "")
        return context


def _detail_context(order: Order) -> dict[str, Any]:
    """Shared by ``OrderDetailView`` and every action view's error path,
    so a rejected edit re-renders the *same* fully-populated detail page
    (with a 400 status) instead of a bare error response."""
    order = (
        Order.objects.select_related("customer")
        .prefetch_related("items", "status_events__actor", "edit_events__actor")
        .get(pk=order.pk)
    )
    try:
        whatsapp_message = build_status_update_message(order)
    except ValueError:
        whatsapp_message = ""
    whatsapp_url = (
        WhatsAppLinkChannel().build_url(
            phone=order.customer_whatsapp_number, message=whatsapp_message
        )
        if whatsapp_message
        else ""
    )
    return {
        "order": order,
        "is_editable": order.status in EDITABLE_STATUSES,
        "allowed_transitions": [
            (value, label)
            for value, label in Order.Status.choices
            if value in ALLOWED_TRANSITIONS.get(order.status, frozenset())
        ],
        "status_transition_form": OrderStatusTransitionForm(),
        "tracking_form": OrderTrackingForm(instance=order),
        "add_line_form": OrderLineAddForm(),
        "whatsapp_status_message": whatsapp_message,
        "whatsapp_status_url": whatsapp_url,
    }


def _render_detail(request: HttpRequest, order: Order, *, status: int = 200) -> HttpResponse:
    return render(request, "portal/order_detail.html", _detail_context(order), status=status)


class OrderDetailView(PortalPermissionRequiredMixin, DetailView[Order]):
    model = Order
    template_name = "portal/order_detail.html"
    context_object_name = "order"
    permission_required = ("orders.view_order",)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        return _detail_context(self.object)


class OrderStatusTransitionView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        form = OrderStatusTransitionForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Choose a valid status.")
            return _render_detail(request, order, status=400)

        try:
            transition_status(
                order=order,
                to_status=form.cleaned_data["to_status"],
                actor=cast(User, request.user),
                note=form.cleaned_data["note"],
            )
        except InvalidStatusTransitionError as exc:
            messages.error(request, str(exc))
            return _render_detail(request, order, status=400)

        messages.success(request, "Order status updated.")
        return redirect("portal:order_detail", pk=pk)


class OrderTrackingUpdateView(PortalPermissionRequiredMixin, View):
    """Tracking number, courier, and merchant notes — plain metadata, not
    gated by ``EDITABLE_STATUSES``. A merchant sets tracking precisely
    when an order reaches Dispatched, which is exactly the point line
    editing becomes blocked."""

    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        form = OrderTrackingForm(request.POST, instance=order)
        if not form.is_valid():
            messages.error(request, "Couldn't save those details.")
            return _render_detail(request, order, status=400)

        form.save()
        messages.success(request, "Tracking details updated.")
        return redirect("portal:order_detail", pk=pk)


class OrderLineQuantityView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        item = get_object_or_404(OrderItem, pk=item_pk, order=order)
        form = OrderLineQuantityForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid quantity.")
            return _render_detail(request, order, status=400)

        try:
            event = editing.change_line_quantity(
                order=order,
                item=item,
                new_quantity=form.cleaned_data["quantity"],
                actor=cast(User, request.user),
            )
        except _LINE_EDIT_ERRORS as exc:
            messages.error(request, str(exc))
            return _render_detail(request, order, status=400)

        if event is None:
            messages.info(request, "Quantity unchanged.")
        else:
            messages.success(request, "Quantity updated.")
        return redirect("portal:order_detail", pk=pk)


class OrderLineRemoveView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        item = get_object_or_404(OrderItem, pk=item_pk, order=order)
        try:
            editing.remove_line(order=order, item=item, actor=cast(User, request.user))
        except (editing.OrderNotEditableError, editing.LineEditError) as exc:
            messages.error(request, str(exc))
            return _render_detail(request, order, status=400)

        messages.success(request, "Line removed.")
        return redirect("portal:order_detail", pk=pk)


class OrderLineAddView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        form = OrderLineAddForm(request.POST)
        if not form.is_valid():
            for error in list(form.errors.get("sku", [])) + list(form.errors.get("quantity", [])):
                messages.error(request, str(error))
            return _render_detail(request, order, status=400)

        try:
            editing.add_line(
                order=order,
                variant=form.cleaned_data["variant"],
                quantity=form.cleaned_data["quantity"],
                actor=cast(User, request.user),
            )
        except _LINE_EDIT_ERRORS as exc:
            messages.error(request, str(exc))
            return _render_detail(request, order, status=400)

        messages.success(request, "Line added.")
        return redirect("portal:order_detail", pk=pk)


class OrderLinePriceView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_order",)

    def post(self, request: HttpRequest, pk: int, item_pk: int) -> HttpResponse:
        order = get_object_or_404(Order, pk=pk)
        item = get_object_or_404(OrderItem, pk=item_pk, order=order)
        form = OrderLinePriceForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a valid price.")
            return _render_detail(request, order, status=400)

        try:
            editing.override_line_price(
                order=order,
                item=item,
                new_unit_price=form.cleaned_data["unit_price"],
                actor=cast(User, request.user),
            )
        except (editing.OrderNotEditableError, editing.LineEditError) as exc:
            messages.error(request, str(exc))
            return _render_detail(request, order, status=400)

        messages.success(request, "Price updated.")
        return redirect("portal:order_detail", pk=pk)
