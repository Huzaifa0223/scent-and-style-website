"""Cart mutation endpoints (roadmap Stage 7) — every one POST-only (no
``get()``, so ``View.dispatch()`` 405s anything else, the same mechanism
used for every other mutation endpoint in this project) and every one
returns the same re-rendered fragment (``cart/_mutation_response.html``):
an out-of-band update to the header badge count, an out-of-band update to
the PDP's inline error slot (a harmless no-op on any page that doesn't have
one), and the drawer's line items as the main response body. Gate 4 — no
page reload on any cart mutation — falls out of every endpoint responding
with a fragment rather than a redirect.
"""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from . import services
from .models import Cart, CartItem


def _parse_positive_int(raw: str | None, *, default: int) -> int:
    if raw is not None and raw.isdigit() and int(raw) > 0:
        return int(raw)
    return default


def _message_for(exc: services.CartMutationError) -> str:
    if exc.available_quantity <= 0:
        return "That item is no longer available."
    return f"Only {exc.available_quantity} left in stock."


def _fragment(request: HttpRequest, cart: Cart | None, *, error: str = "") -> HttpResponse:
    lines = services.cart_lines(cart) if cart is not None else []
    context = {
        "cart_lines": lines,
        "cart_item_count": sum(line.item.quantity for line in lines),
        "cart_subtotal": services.cart_subtotal(lines),
        "error": error,
    }
    return render(request, "cart/_mutation_response.html", context)


def _get_cart_or_404(request: HttpRequest) -> Cart:
    cart = services.get_cart(request)
    if cart is None:
        raise Http404("No cart for this session.")
    return cart


def _get_item_or_404(cart: Cart, item_id: int) -> CartItem:
    return get_object_or_404(cart.items, pk=item_id)


class CartAddView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        cart = services.get_or_create_cart(request)
        variant_id_raw = request.POST.get("variant_id", "")
        if not variant_id_raw.isdigit():
            return _fragment(request, cart, error="Couldn't add that item.")

        quantity = _parse_positive_int(request.POST.get("quantity"), default=1)
        try:
            services.add_item(cart, variant_id=int(variant_id_raw), quantity=quantity)
        except services.CartMutationError as exc:
            return _fragment(request, cart, error=_message_for(exc))
        return _fragment(request, cart)


class CartIncrementView(View):
    def post(self, request: HttpRequest, item_id: int) -> HttpResponse:
        cart = _get_cart_or_404(request)
        item = _get_item_or_404(cart, item_id)
        try:
            services.increment_item(item)
        except services.CartMutationError as exc:
            return _fragment(request, cart, error=_message_for(exc))
        return _fragment(request, cart)


class CartDecrementView(View):
    def post(self, request: HttpRequest, item_id: int) -> HttpResponse:
        cart = _get_cart_or_404(request)
        item = _get_item_or_404(cart, item_id)
        services.decrement_item(item)
        return _fragment(request, cart)


class CartRemoveView(View):
    def post(self, request: HttpRequest, item_id: int) -> HttpResponse:
        cart = _get_cart_or_404(request)
        item = _get_item_or_404(cart, item_id)
        services.remove_item(item)
        return _fragment(request, cart)


class CartClearView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        cart = _get_cart_or_404(request)
        services.clear_cart(cart)
        return _fragment(request, cart)
