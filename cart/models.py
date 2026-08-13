"""Cart domain model (requirements §19, roadmap Stage 7).

Server-side and session-keyed, deliberately not ``localStorage``: stock can
be validated authoritatively on every mutation, the cart survives a device
switch within a session, and abandoned-cart recovery (§49) stays possible
without a rewrite.

``CartItem.variant`` FKs to ``ProductVariant``, never ``Product`` — CLAUDE.md's
locked "variants are the purchasable unit" decision applies here exactly as
it does to ``StockReservation`` and (from Stage 8) ``OrderItem``.
"""

from __future__ import annotations

from django.db import models

from catalog.models import ProductVariant
from core.models import TimeStampedModel


class Cart(TimeStampedModel):
    """One row per browser session that has ever added an item. Rows are
    created lazily on first add, not on every visit — see
    ``cart.services.get_cart()`` vs ``get_or_create_cart()``, since forcing
    a session (and a cart row) into existence for every anonymous visitor
    who never adds anything would be a write on every page view for no
    reason."""

    session_key = models.CharField(max_length=40, unique=True, db_index=True)

    def __str__(self) -> str:
        return f"Cart({self.session_key})"


class CartItem(TimeStampedModel):
    """``variant`` is ``on_delete=SET_NULL`` and nullable — deleting the
    variant a customer already added must not cascade into deleting their
    cart item (or the cart row, or crashing the cart view with a dangling
    FK). A ``NULL`` variant is exactly the "this item is no longer
    available" case the drawer renders explicitly rather than 500ing on
    (roadmap Stage 7 gate 3) — see ``cart.services.cart_lines()``.

    The unique constraint tolerates multiple ``NULL`` variants per cart
    (Postgres treats each ``NULL`` as distinct in a unique index), which is
    exactly right here: two line items that both lost their variant are two
    separate, independently removable rows, not a collision.
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, related_name="cart_items"
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "variant"], name="cartitem_unique_cart_variant"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="cartitem_quantity_gte_1"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x variant#{self.variant_id}"
