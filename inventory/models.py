"""Inventory domain model (requirements §10) — reservation with a TTL,
never a permanent decrement at order creation and never a decrement at
confirmation without first reserving. See ``inventory/services.py`` for
the actual state-machine logic; this module is deliberately just the two
tables.

``StockReservation.order`` was added in Stage 8, once ``orders.Order``
existed to point at (Django cannot define a ``ForeignKey`` to a model in
an app that isn't installed). Nullable at the DB level — required for
``AddField`` on an already-populated table — but every real reservation
from Stage 8 onward has one: ``inventory.services.reserve()`` takes
``order`` as a required keyword argument, and it's the only place a
``StockReservation`` is ever created.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from catalog.models import ProductVariant
from core.models import TimeStampedModel


class StockReservation(TimeStampedModel):
    """One line's worth of reserved stock, created at order creation and
    consumed (deleted) by exactly one of: ``commit_reservation`` (order
    confirmed), ``release`` (order cancelled while pending), or the
    sweeper (TTL elapsed). ``expires_at`` is indexed because both the
    sweeper's bulk delete and every availability check filter on it.

    ``order`` is ``on_delete=CASCADE`` — a reservation with no surviving
    order is meaningless; if an order row is ever deleted, its held
    reservations should go with it rather than linger as orphans.
    """

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="reservations"
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, null=True, related_name="reservations"
    )
    quantity = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["expires_at"]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.variant.sku} (expires {self.expires_at:%Y-%m-%d %H:%M})"


class InventoryAdjustment(TimeStampedModel):
    """Append-only audit row for every real change to ``stock_quantity`` —
    manual corrections and the two order-driven cases (confirmed,
    cancelled/returned after confirmation). Reservation create/release
    never touches ``stock_quantity``, so those never write a row here;
    only actual on-hand changes do.

    ``actor`` is nullable + ``SET_NULL`` so the audit trail survives a
    deleted user account — losing who made a change is worse than losing
    the FK, but the row itself must never disappear (append-only, per the
    later ``audit.AuditLog`` app's own "no update or delete path" rule,
    which this model already follows in spirit)."""

    class Reason(models.TextChoices):
        MANUAL = "manual", "Manual adjustment"
        ORDER_CONFIRMED = "order_confirmed", "Order confirmed"
        ORDER_CANCELLED = "order_cancelled", "Order cancelled after confirmation"
        ORDER_RETURNED = "order_returned", "Order returned"

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="adjustments"
    )
    delta = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inventory_adjustments",
    )
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{self.variant.sku} {sign}{self.delta} ({self.reason})"
