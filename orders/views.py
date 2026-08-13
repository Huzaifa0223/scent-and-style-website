"""Checkout views (§20-22, roadmap Stage 8) — public, no permission mixin
(same as everything in ``storefront``).
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View

from cart import services as cart_services
from cart.services import CartLine
from notifications.whatsapp.channel import WhatsAppLinkChannel
from notifications.whatsapp.message_builder import build_order_confirmation_message
from store.models import StoreSettings

from .forms import CheckoutForm
from .models import Order
from .services import CheckoutInput, CheckoutValidationError, EmptyCartError, create_order


class CheckoutView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        cart = cart_services.get_cart(request)
        lines = cart_services.cart_lines(cart) if cart is not None else []
        if not lines:
            messages.info(request, "Your cart is empty.")
            return redirect("storefront:product_list")
        return self._render(request, CheckoutForm(), lines)

    def post(self, request: HttpRequest) -> HttpResponse:
        cart = cart_services.get_cart(request)
        lines = cart_services.cart_lines(cart) if cart is not None else []
        if cart is None or not lines:
            messages.info(request, "Your cart is empty.")
            return redirect("storefront:product_list")

        form = CheckoutForm(request.POST)
        if not form.is_valid():
            return self._render(request, form, lines)

        checkout_input = CheckoutInput(
            name=form.cleaned_data["name"],
            phone=form.cleaned_data["mobile_number"],
            whatsapp_number=form.cleaned_data["whatsapp_number"],
            email=form.cleaned_data.get("email", ""),
            address=form.cleaned_data["address"],
            city=form.cleaned_data["city"],
            postal_code=form.cleaned_data.get("postal_code", ""),
            instructions=form.cleaned_data.get("instructions", ""),
            notes=form.cleaned_data.get("notes", ""),
        )

        try:
            order = create_order(cart=cart, checkout_input=checkout_input)
        except EmptyCartError:
            messages.info(request, "Your cart is empty.")
            return redirect("storefront:product_list")
        except CheckoutValidationError as exc:
            return self._render(
                request, form, cart_services.cart_lines(cart), checkout_errors=exc.errors
            )

        request.session["last_order_id"] = order.pk
        return redirect("orders:confirmation", order_number=order.order_number)

    def _render(
        self,
        request: HttpRequest,
        form: CheckoutForm,
        lines: list[CartLine],
        *,
        checkout_errors: list[Any] | None = None,
    ) -> HttpResponse:
        context = {
            "form": form,
            "cart_lines": lines,
            "checkout_subtotal": cart_services.cart_subtotal(lines),
            "checkout_errors": checkout_errors or [],
        }
        return render(request, "orders/checkout.html", context)


class OrderConfirmationView(View):
    """Scoped to ``request.session["last_order_id"]`` — set only by
    ``CheckoutView`` immediately after a successful ``create_order()`` —
    so this is not a general order-lookup-by-number endpoint. Only
    ~30,000 order-number suffix combinations exist (§22), and Stage 11's
    actual rate-limited public tracking page doesn't exist yet; this view
    must not become that page ahead of schedule.
    """

    def get(self, request: HttpRequest, order_number: str) -> HttpResponse:
        last_order_id = request.session.get("last_order_id")
        if last_order_id is None:
            raise Http404("No order to confirm in this session.")
        order = get_object_or_404(
            Order.objects.prefetch_related("items"),
            pk=last_order_id,
            order_number=order_number,
        )
        # The order already exists in the database (created before this
        # view is ever reached — orders.services.create_order() commits
        # first, this page only renders afterward) regardless of whether
        # the WhatsApp link below is ever opened or the message ever
        # sent. §21: "the order exists in the merchant system before
        # WhatsApp opens."
        whatsapp_message = build_order_confirmation_message(order)
        merchant_whatsapp_number = StoreSettings.load().whatsapp_number
        # A blank merchant number would make WhatsAppLinkChannel produce
        # a phoneless deep link — a real, documented WhatsApp behaviour
        # (opens the message ready to send to any contact) but the wrong
        # one here specifically: this link exists to reach *the
        # merchant*, and an unaddressed link achieves nothing for that.
        # Omit the button entirely rather than offer one that can't do
        # its job; the order number and the copyable message text
        # remain the fallback regardless.
        whatsapp_url = (
            WhatsAppLinkChannel().build_url(
                phone=merchant_whatsapp_number, message=whatsapp_message
            )
            if merchant_whatsapp_number
            else ""
        )
        context = {
            "order": order,
            "whatsapp_url": whatsapp_url,
            "whatsapp_message": whatsapp_message,
        }
        return render(request, "orders/order_confirmation.html", context)
