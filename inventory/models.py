"""Inventory domain model (requirements §10) — reservation with a TTL,
never a permanent decrement at order creation and never a decrement at
confirmation without first reserving. See ``inventory/services.py`` for
the actual state-machine logic; this module is deliberately just the two
tables.

``StockReservation`` has no ``order`` FK yet. The roadmap's Stage 4
deliverable list says "order FK nullable until stage 8", but ``orders.
Order`` does not exist until Stage 8 builds it — Django cannot define a
``ForeignKey`` to a model in an app that isn't installed (``manage.py
check`` would fail with E300). Read as describing the field's eventual
shape rather than something Stage 4 can literally build; the field is
added via ``AddField`` when Stage 8 creates ``orders.Order``. Recorded as
a proposed spec amendment in ``specs/state.md``.
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
    sweeper's bulk delete and every availability check filter on it."""

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="reservations"
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
