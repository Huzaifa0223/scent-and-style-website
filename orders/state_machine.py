"""Order status transitions (§23) — ``transition_status()`` is the only
sanctioned way to change ``Order.status``. Locks the order row first (the
same "serialize concurrent mutation of one order" reasoning
``orders.services.create_order()`` already uses for ``Cart``), validates
against ``orders.status.ALLOWED_TRANSITIONS``, then — depending on which
edge is being taken — hands off to the matching bulk function in
``inventory.services``. This module never imports ``StockReservation``
itself; every stock-affecting side effect of a transition goes through a
named ``inventory.services`` call.
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import transaction

from inventory import services as inventory_services
from inventory.models import InventoryAdjustment

from .models import Order, OrderStatusEvent
from .status import ALLOWED_TRANSITIONS, Status


class InvalidStatusTransitionError(Exception):
    def __init__(self, *, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition an order from {from_status!r} to {to_status!r}.")


@transaction.atomic
def transition_status(*, order: Order, to_status: str, actor: User | None, note: str = "") -> Order:
    """Validate and apply one status transition, writing the
    ``OrderStatusEvent`` and any stock side effect in the same
    transaction as the status write itself — a failure partway (an
    ``InsufficientStockError`` cannot actually occur here, since these
    calls only ever release or restore stock, never reserve more of it,
    but a future edge that does add a reserving transition inherits this
    atomicity for free) must never leave the status changed with no
    matching audit row, or vice versa.
    """
    locked_order = Order.objects.select_for_update().get(pk=order.pk)
    from_status = locked_order.status
    allowed = ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise InvalidStatusTransitionError(from_status=from_status, to_status=to_status)

    if to_status == Status.CONFIRMED:
        inventory_services.commit_all_for_order(order=locked_order, actor=actor)
    elif from_status == Status.PENDING_CONFIRMATION and to_status in (
        Status.CANCELLED,
        Status.EXPIRED,
    ):
        # Still pending — stock was only ever reserved, never decremented.
        inventory_services.release_all_for_order(order=locked_order)
    elif to_status == Status.CANCELLED:
        # Cancelled from any later status (Confirmed, Processing, Ready to
        # Dispatch, Failed Delivery — every one of them reachable only
        # after Confirmed already ran commit_all_for_order()) means stock
        # is a permanent decrement with no reservation left to release;
        # give it back. Not just the Confirmed->Cancelled edge specifically
        # — every "cancel" edge past Pending Confirmation needs this, or
        # cancelling from Processing/Ready to Dispatch/Failed Delivery
        # would silently leave stock decremented forever.
        inventory_services.restore_all_for_order(
            order=locked_order, reason=InventoryAdjustment.Reason.ORDER_CANCELLED, actor=actor
        )
    elif to_status == Status.RETURNED:
        inventory_services.restore_all_for_order(
            order=locked_order, reason=InventoryAdjustment.Reason.ORDER_RETURNED, actor=actor
        )

    locked_order.status = to_status
    locked_order.save(update_fields=["status", "updated_at"])
    OrderStatusEvent.objects.create(
        order=locked_order, from_status=from_status, to_status=to_status, actor=actor, note=note
    )
    return locked_order
