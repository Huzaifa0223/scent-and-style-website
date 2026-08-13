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


@transaction.atomic
def release_reserved(*, variant_id: int, order: Order, quantity: int) -> None:
    """Release exactly ``quantity`` units of ``order``'s own active
    reservations against ``variant`` — the counterpart ``release()``
    doesn't provide: that function deletes one whole reservation row by
    id, but a quantity-*down* edit on a still-pending order may need to
    give back fewer units than a single row holds (roadmap Stage 10:
    "increasing a line quantity must reserve the delta... decreasing must
    release it"). Consumes rows oldest-first, deleting a row once it's
    fully released and shrinking the last partially-consumed one.

    Locks the variant row first, same as every other write in this
    module — so this can never race a concurrent ``reserve()`` or
    ``commit_reservation()`` for the same variant.
    """
    if quantity <= 0:
        raise ValidationError("quantity must be a positive integer.")

    ProductVariant.objects.select_for_update().get(pk=variant_id)
    reservations = list(
        StockReservation.objects.select_for_update()
        .filter(variant_id=variant_id, order=order, expires_at__gt=Now())
        .order_by("pk")
    )

    remaining = quantity
    for reservation in reservations:
        if remaining <= 0:
            break
        if reservation.quantity <= remaining:
            remaining -= reservation.quantity
            reservation.delete()
        else:
            reservation.quantity -= remaining
            reservation.save(update_fields=["quantity", "updated_at"])
            remaining = 0

    if remaining > 0:
        raise ValidationError(
            f"Cannot release {quantity} unit(s) of variant {variant_id} for order "
            f"{order.order_number}: only {quantity - remaining} were reserved for it."
        )


@transaction.atomic
def consume(
    *,
    variant_id: int,
    quantity: int,
    reason: InventoryAdjustment.Reason,
    actor: User | None = None,
    note: str = "",
) -> None:
    """Directly decrement on-hand stock, with the same availability check
    ``reserve()`` uses, but no reservation row — for a quantity-*up* edit
    on an already-``Confirmed`` order. A confirmed order's stock is
    already a permanent decrement (``commit_reservation()`` deleted its
    reservation), so there is nothing left to add a delta reservation to;
    increasing that commitment must recheck availability against *other*
    orders' active reservations and decrement ``stock_quantity`` directly,
    under the variant's row lock, so two concurrent edits against the
    last unit still serialize correctly.
    """
    if quantity <= 0:
        raise ValidationError("quantity must be a positive integer.")

    variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    available = variant.stock_quantity - _active_reserved_quantity(variant)
    if available < quantity:
        raise InsufficientStockError(
            f"Only {available} unit(s) of {variant.sku} available, {quantity} requested."
        )

    variant.stock_quantity -= quantity
    variant.save(update_fields=["stock_quantity", "updated_at"])
    _write_adjustment(variant, delta=-quantity, reason=reason, actor=actor, note=note)


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


def commit_all_for_order(*, order: Order, actor: User | None = None) -> None:
    """Confirm every reservation ``order`` still holds — called when an
    order transitions ``Pending Confirmation`` -> ``Confirmed``. Iterates
    rather than a bulk update so each row still goes through
    ``commit_reservation()``'s own lock and audit write, unchanged; a
    caller in ``orders/`` never touches ``StockReservation`` itself."""
    reservation_ids = StockReservation.objects.filter(order=order).values_list("pk", flat=True)
    for reservation_id in list(reservation_ids):
        commit_reservation(reservation_id=reservation_id, actor=actor)


def release_all_for_order(*, order: Order) -> None:
    """Release every reservation ``order`` still holds, without touching
    on-hand stock — called when a still-``Pending Confirmation`` order is
    cancelled or expires."""
    reservation_ids = StockReservation.objects.filter(order=order).values_list("pk", flat=True)
    for reservation_id in list(reservation_ids):
        release(reservation_id=reservation_id)


def restore_all_for_order(
    *, order: Order, reason: InventoryAdjustment.Reason, actor: User | None = None
) -> None:
    """Give back exactly each line's current quantity of on-hand stock —
    called when a ``Confirmed`` order is cancelled, or a ``Delivered`` one
    is returned. Skips a line whose ``variant`` is ``None`` (the product
    was deleted) — there is no ``ProductVariant`` row left to credit, and
    that deletion already means the stock it once represented isn't
    tracked here anymore."""
    for item in order.items.all():
        if item.variant_id is not None:
            restore(variant_id=item.variant_id, quantity=item.quantity, reason=reason, actor=actor)


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
