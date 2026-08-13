"""Order status state machine (§23) — the allowed-transition map and the
set of statuses order editing is permitted in. Typed config, per CLAUDE.md
("no magic numbers... thresholds live in typed config"), scoped to
``orders/`` rather than ``core/config.py`` because it's expressed directly
in terms of ``Order.Status`` — ``core`` holds only cross-cutting,
domain-agnostic constants, never one app's own business rules.

The map reads §23's literal chain
(``Pending Confirmation -> Confirmed -> Processing -> Ready to Dispatch ->
Dispatched -> Out for Delivery -> Delivered``) as *sequential*, not
skip-ahead — each status may only advance to the next step in the chain or
to a terminal/exceptional state reachable from it. A merchant workflow
that wants to skip "Ready to Dispatch" entirely is a product decision the
spec doesn't make; recorded as an open question in specs/state.md rather
than invented here.

``EDITABLE_STATUSES`` reads requirements §23's own two sentences
literally: "While an order is Pending Confirmation or Confirmed, the
merchant may..." is the operative rule (a whitelist of exactly two
statuses), and "editing is blocked once the order is Dispatched or
beyond" is a restatement, not a looser grant covering Processing or Ready
to Dispatch too.
"""

from __future__ import annotations

from typing import Final

from .models import Order

Status = Order.Status

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    Status.PENDING_CONFIRMATION: frozenset({Status.CONFIRMED, Status.CANCELLED, Status.EXPIRED}),
    Status.CONFIRMED: frozenset({Status.PROCESSING, Status.CANCELLED}),
    Status.PROCESSING: frozenset({Status.READY_TO_DISPATCH, Status.CANCELLED}),
    Status.READY_TO_DISPATCH: frozenset({Status.DISPATCHED, Status.CANCELLED}),
    Status.DISPATCHED: frozenset({Status.OUT_FOR_DELIVERY, Status.FAILED_DELIVERY}),
    Status.OUT_FOR_DELIVERY: frozenset({Status.DELIVERED, Status.FAILED_DELIVERY}),
    Status.FAILED_DELIVERY: frozenset({Status.OUT_FOR_DELIVERY, Status.CANCELLED}),
    Status.DELIVERED: frozenset({Status.RETURNED}),
    Status.CANCELLED: frozenset(),
    Status.RETURNED: frozenset(),
    Status.EXPIRED: frozenset(),
}

EDITABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {Status.PENDING_CONFIRMATION, Status.CONFIRMED}
)
