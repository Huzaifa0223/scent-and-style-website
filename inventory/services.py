"""Inventory service functions (requirements §10) — the only sanctioned way
to change ``ProductVariant.stock_quantity`` or create/consume a
``StockReservation``. Every function that reads availability and then
writes takes ``select_for_update()`` on the variant row inside an explicit
transaction (§10.2) — that lock is what makes "available" authoritative
rather than a stale read racing another request for the same unit.

Three call sites decide "is this reservation still active" — this module's
own ``reserve()``, ``catalog.models.ProductVariantQuerySet.
with_available_quantity()``, and ``release_expired_reservations()`` below —
and all three compare against the database's clock (``Now()``), never
Python's ``timezone.now()``, for exactly one reason: a Python-side
timestamp captured at the wrong point (module import, a class attribute) is
one refactor away from freezing "now" at process start, and three call
sites silently using two different clocks to answer the same question is a
real bug waiting to happen, not a hypothetical one.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Now
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import Order
from store.models import StoreSettings

from .models import InventoryAdjustment, StockReservation


class InsufficientStockError(Exception):
    """Raised by ``reserve()`` when fewer units are available than
    requested, computed under the variant's row lock — authoritative, not
    a stale read from before some other request's reservation landed."""


def _active_reserved_quantity(variant: ProductVariant) -> int:
    """Sum of unexpired reservations against an already-locked variant.
    Callers must hold the row lock (``select_for_update()``) before
    calling this — it does not take one itself, so it never issues the
    lock on its own and can be reused inside a caller's own transaction.
    """
    total = variant.reservations.filter(expires_at__gt=Now()).aggregate(total=Sum("quantity"))[
        "total"
    ]
    return total or 0


def _write_adjustment(
    variant: ProductVariant,
    *,
    delta: int,
    reason: InventoryAdjustment.Reason,
    actor: User | None,
    note: str,
) -> None:
    InventoryAdjustment.objects.create(
        variant=variant, delta=delta, reason=reason, actor=actor, note=note
    )


@transaction.atomic
def reserve(
    *, variant_id: int, quantity: int, order: Order, ttl_hours: int | None = None
) -> StockReservation:
    """Create a ``StockReservation`` for ``quantity`` units of the variant,
    or raise ``InsufficientStockError`` if fewer are available. Never
    touches ``stock_quantity`` — reservation is a promise against on-hand
    stock, not a decrement of it (§10.1's whole reason to exist: decrement
    at order creation permanently locks stock behind abandoned WhatsApp
    orders, decrement at confirmation lets two customers both "win" the
    last unit).

    ``order`` is required (Stage 8) — every reservation exists to hold
    stock for a specific order, and this is the only function that ever
    creates a ``StockReservation``, so there is no legitimate caller left
    that wouldn't have one. This is also the actual concurrency-safety
    mechanism for order creation (``orders.services.create_order``):
    ``select_for_update()`` below serializes against *any* other writer
    to this variant row, including a second, concurrent ``reserve()``
    call for the same variant — not just against callers that also take
    the same lock by convention."""
    if quantity <= 0:
        raise ValidationError("quantity must be a positive integer.")

    variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    available = variant.stock_quantity - _active_reserved_quantity(variant)
    if available < quantity:
        raise InsufficientStockError(
            f"Only {available} unit(s) of {variant.sku} available, {quantity} requested."
        )

    ttl = ttl_hours if ttl_hours is not None else StoreSettings.load().reservation_ttl_hours
    return StockReservation.objects.create(
        variant=variant,
        order=order,
        quantity=quantity,
        expires_at=timezone.now() + timedelta(hours=ttl),
    )


def release(*, reservation_id: int) -> None:
    """Delete a reservation without touching ``stock_quantity`` — used for
    a merchant-cancelled pending order and, via
    ``release_expired_reservations()``, an expired one. Unconditional
    ``filter().delete()`` rather than ``get()`` + ``delete()``: a
    double-release (the merchant cancels the same order twice, or a race
    with the sweeper) is a silent no-op, not a ``DoesNotExist`` — no lock
    needed, since releasing never depends on reading current availability
    to decide whether it's valid."""
    StockReservation.objects.filter(pk=reservation_id).delete()


@transaction.atomic
def commit_reservation(*, reservation_id: int, actor: User | None = None) -> None:
    """Called when the merchant confirms the order: decrements
    ``stock_quantity`` by the reservation's own quantity, deletes the
    reservation, and writes the audit row — all under the variant's row
    lock so a concurrent manual adjustment can't race this write."""
    reservation = StockReservation.objects.get(pk=reservation_id)
    variant = ProductVariant.objects.select_for_update().get(pk=reservation.variant_id)

    new_quantity = variant.stock_quantity - reservation.quantity
    if new_quantity < 0:
        raise ValidationError(
            f"Cannot confirm: {variant.sku} has {variant.stock_quantity} on hand, "
            f"reservation is for {reservation.quantity}."
        )

    variant.stock_quantity = new_quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    reservation.delete()
    _write_adjustment(
        variant,
        delta=-reservation.quantity,
        reason=InventoryAdjustment.Reason.ORDER_CONFIRMED,
        actor=actor,
        note="",
    )


@transaction.atomic
def restore(
    *,
    variant_id: int,
    quantity: int,
    reason: InventoryAdjustment.Reason,
    actor: User | None = None,
    note: str = "",
) -> None:
    """Increments ``stock_quantity`` — used when a confirmed order is
    later cancelled or returned, giving back stock that was already
    decremented by ``commit_reservation()``. ``reason`` is caller-supplied
    (``ORDER_CANCELLED`` vs ``ORDER_RETURNED``) since that distinction
    belongs to the order workflow (Stage 8/10), not to this service."""
    if quantity <= 0:
        raise ValidationError("quantity must be a positive integer.")

    variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    variant.stock_quantity += quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    _write_adjustment(variant, delta=quantity, reason=reason, actor=actor, note=note)


@transaction.atomic
def adjust(
    *, variant_id: int, absolute_quantity: int, actor: User | None = None, note: str = ""
) -> ProductVariant:
    """Merchant sets a new on-hand count directly (§10.1: "set
    stock_quantity directly") — ``absolute_quantity`` is the new total,
    not a delta, deliberately named to not be confused with ``restore()``'s
    ``quantity``, which *is* a delta. The audit row's own ``delta`` is
    computed here from the difference. ``reason`` is always ``MANUAL``,
    not a caller parameter — this path is only ever taken for manual
    counts, so there's no ambiguity for a caller to resolve."""
    if absolute_quantity < 0:
        raise ValidationError("absolute_quantity cannot be negative.")

    variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    delta = absolute_quantity - variant.stock_quantity
    if delta == 0:
        return variant

    variant.stock_quantity = absolute_quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    _write_adjustment(
        variant, delta=delta, reason=InventoryAdjustment.Reason.MANUAL, actor=actor, note=note
    )
    return variant


def release_expired_reservations() -> int:
    """Bulk-delete every reservation past its TTL and return the count.
    No ``select_for_update()``: a bulk ``DELETE ... WHERE expires_at <=
    now()`` is self-atomic at the statement level, and safe to run
    concurrently with itself by construction — two sweepers racing each
    other simply both issue the same statement; whichever commits first
    deletes the matching rows, the other matches zero of them and returns
    0. No lock contention beyond what Postgres already does for any
    DELETE, no double-processing, no error path."""
    deleted_count, _ = StockReservation.objects.filter(expires_at__lte=Now()).delete()
    return deleted_count
