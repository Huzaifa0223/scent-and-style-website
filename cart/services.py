"""Cart service functions (requirements §19, roadmap Stage 7) — the only
sanctioned way to read or mutate a cart's contents.

Every availability question here is answered by
``catalog.models.ProductVariantQuerySet.with_available_quantity()``, never
by reading ``ProductVariant.stock_quantity`` directly — that annotation is
Stage 4's own inventory-reservation math (active, unexpired
``StockReservation`` rows subtracted from on-hand stock), and duplicating
that logic here would be a second, divergeable answer to "how many can
still be bought" living next to the first one. The cart is that layer's
first real consumer outside ``inventory``/``portal`` itself.

Availability here is advisory, not authoritative: adding to a cart never
creates a ``StockReservation`` (CLAUDE.md's locked decision — stock is
reserved at *order* creation, Stage 8's job) and never takes a row lock.
Checkout re-validates under ``select_for_update()`` at submit time; this
layer's job is to keep the cart's displayed state honest between now and
then, not to guarantee a unit is still there when the customer finally
checks out.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.http import HttpRequest

from catalog.models import ProductVariant

from .models import Cart, CartItem


class CartMutationError(Exception):
    """Raised by ``add_item()``/``increment_item()`` when the requested
    quantity exceeds what's actually available. Carries the real available
    number (0 for a deleted or deactivated variant) so the view can put it
    in a specific, actionable message (gate 1) rather than a generic
    "couldn't add that" — the same reasoning CLAUDE.md's §44 states for
    storefront errors generally."""

    def __init__(self, *, available_quantity: int) -> None:
        self.available_quantity = available_quantity
        super().__init__(f"Only {available_quantity} unit(s) available.")


@dataclass(frozen=True)
class CartLine:
    """One row in the rendered cart — a ``CartItem`` plus everything the
    template needs to decide what to show, computed once here rather than
    re-derived (differently) in every template that renders a cart line.

    ``variant`` is ``None`` exactly when the underlying ``ProductVariant``
    has been deleted (``on_delete=SET_NULL``) — gate 3's "deleted" case.
    ``purchasable_quantity`` is 0 for that case and for a deactivated
    variant, same as an out-of-stock one — gate 3's "deactivated" case
    collapses into the same handling as gate 2's "went out of stock"
    case, deliberately: from the cart's perspective a variant nobody can
    buy right now is one condition with three causes, not three.
    """

    item: CartItem
    variant: ProductVariant | None
    purchasable_quantity: int
    unavailable_reason: str
    line_total: Decimal

    @property
    def needs_attention(self) -> bool:
        return self.purchasable_quantity < self.item.quantity


def get_cart(request: HttpRequest) -> Cart | None:
    """Read-only lookup — never creates a session or a ``Cart`` row.
    Returns ``None`` for a visitor who has never added anything, which
    every caller renders as an empty cart rather than treating as an
    error. Also ``None`` if ``request`` was never run through
    ``SessionMiddleware`` at all (no ``.session`` attribute) — every real
    request has one (it's in ``MIDDLEWARE`` unconditionally), but a request
    built directly via ``RequestFactory`` to unit-test template rendering
    in isolation, bypassing the middleware chain entirely, does not; this
    function is reached from the globally-registered ``cart`` context
    processor on every template render, including those tests'."""
    session = getattr(request, "session", None)
    session_key = session.session_key if session is not None else None
    if not session_key:
        return None
    return Cart.objects.filter(session_key=session_key).first()


def get_or_create_cart(request: HttpRequest) -> Cart:
    """The only path that creates a ``Cart`` row — called from mutation
    views only, never from a plain page render, so browsing the storefront
    doesn't write a session and a cart row for every visitor who never
    adds anything."""
    if not request.session.session_key:
        request.session.create()
    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key)
    return cart


def _reason(variant: ProductVariant | None, purchasable_quantity: int, requested: int) -> str:
    if variant is None or not variant.is_active:
        return "This item is no longer available."
    if purchasable_quantity <= 0:
        return "Out of stock."
    if purchasable_quantity < requested:
        return f"Only {purchasable_quantity} left — update the quantity."
    return ""


def cart_lines(cart: Cart) -> list[CartLine]:
    """Every line in one pass, two queries total regardless of item count
    (the cart's own items, then every referenced variant's availability in
    a single ``with_available_quantity()`` query) — flat under
    ``assertNumQueries`` as the cart grows, the same discipline every other
    list-rendering view in this project already holds itself to."""
    items = list(cart.items.all())
    variant_ids = [item.variant_id for item in items if item.variant_id is not None]
    variants_by_id = {
        variant.pk: variant
        for variant in ProductVariant.objects.with_available_quantity()
        .select_related("product")
        .filter(pk__in=variant_ids)
    }

    lines: list[CartLine] = []
    for item in items:
        variant = variants_by_id.get(item.variant_id) if item.variant_id is not None else None
        if variant is not None and variant.is_active:
            purchasable = min(item.quantity, variant.available_quantity)  # type: ignore[attr-defined]
        else:
            purchasable = 0
        reason = _reason(variant, purchasable, item.quantity)
        line_total = (variant.price * purchasable) if variant is not None else Decimal("0.00")
        lines.append(
            CartLine(
                item=item,
                variant=variant,
                purchasable_quantity=purchasable,
                unavailable_reason=reason,
                line_total=line_total,
            )
        )
    return lines


def cart_subtotal(lines: list[CartLine]) -> Decimal:
    return sum((line.line_total for line in lines), Decimal("0.00"))


def add_item(cart: Cart, *, variant_id: int, quantity: int = 1) -> CartItem:
    variant = ProductVariant.objects.with_available_quantity().filter(pk=variant_id).first()
    if variant is None or not variant.is_active:
        raise CartMutationError(available_quantity=0)

    existing = cart.items.filter(variant_id=variant_id).first()
    requested_total = quantity + (existing.quantity if existing else 0)
    if requested_total > variant.available_quantity:  # type: ignore[attr-defined]
        raise CartMutationError(available_quantity=variant.available_quantity)  # type: ignore[attr-defined]

    if existing is not None:
        existing.quantity = requested_total
        existing.save(update_fields=["quantity", "updated_at"])
        return existing
    return cart.items.create(variant_id=variant_id, quantity=quantity)


def increment_item(item: CartItem, *, by: int = 1) -> CartItem:
    if item.variant_id is None:
        raise CartMutationError(available_quantity=0)

    variant = ProductVariant.objects.with_available_quantity().filter(pk=item.variant_id).first()
    if variant is None or not variant.is_active:
        raise CartMutationError(available_quantity=0)

    new_quantity = item.quantity + by
    if new_quantity > variant.available_quantity:  # type: ignore[attr-defined]
        raise CartMutationError(available_quantity=variant.available_quantity)  # type: ignore[attr-defined]

    item.quantity = new_quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def decrement_item(item: CartItem, *, by: int = 1) -> CartItem | None:
    """Always allowed regardless of the variant's availability — a
    customer must always be able to reduce or clear a line that's no
    longer purchasable, only *adding more* of one is gated."""
    new_quantity = item.quantity - by
    if new_quantity <= 0:
        item.delete()
        return None
    item.quantity = new_quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def remove_item(item: CartItem) -> None:
    item.delete()


def clear_cart(cart: Cart) -> None:
    cart.items.all().delete()
