"""Private POS API (``/api/pos/sync/``): bearer ``SCENT_POS_TOKEN`` (separate
from the tablets' ``SCENT_SYNC_TOKEN``), ~30 req/min/IP, HTTPS only outside
DEBUG, CSRF-exempt, and **no CORS headers** — the same pipeline as the
kiosk API (``noor.security``), because the client is a native POS program,
not a browser.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from noor.http import error_response, json_response
from noor.security import ViewFunc, bearer_endpoint
from orders.models import Order

from . import services
from .config import (
    POS_RATE_LIMIT_SCOPE,
    POS_TOKEN_SETTING,
    SNAPSHOT_FUTURE_TOLERANCE,
    SNAPSHOT_MAX_BYTES,
)
from .services import AckConflictError, OrderNotAwaitingAckError, SnapshotItem

logger = logging.getLogger(__name__)

SALE_NUMBER_MAX_LENGTH = 64
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def pos_endpoint(*methods: str) -> Callable[[ViewFunc], ViewFunc]:
    return bearer_endpoint(*methods, token_setting=POS_TOKEN_SETTING, scope=POS_RATE_LIMIT_SCOPE)


class PayloadError(Exception):
    """A rejected request body: 400 (or 413) with a machine-readable code,
    plus the offending item index when one item is at fault."""

    def __init__(self, code: str, index: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.index = index

    def response(self) -> HttpResponse:
        status = 413 if self.code == "payload_too_large" else 400
        body: dict[str, Any] = {"error": self.code}
        if self.index is not None:
            body["index"] = self.index
        return json_response(body, status=status)


def _read_json_object(request: HttpRequest) -> dict[str, Any]:
    """Body read from the stream, like noor's backup upload: ``request.body``
    would refuse anything over Django's 2.5 MB default."""
    declared = request.META.get("CONTENT_LENGTH", "")
    if declared.isdigit() and int(declared) > SNAPSHOT_MAX_BYTES:
        raise PayloadError("payload_too_large")
    raw = request.read(SNAPSHOT_MAX_BYTES + 1)
    if len(raw) > SNAPSHOT_MAX_BYTES:
        raise PayloadError("payload_too_large")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise PayloadError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise PayloadError("invalid_json")
    return payload


def _parse_snapshot_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise PayloadError("invalid_snapshot_at")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PayloadError("invalid_snapshot_at") from exc
    if timezone.is_naive(moment):
        # A POS that omits the offset means its own (shop) local time.
        moment = timezone.make_aware(moment)
    if moment > timezone.now() + SNAPSHOT_FUTURE_TOLERANCE:
        raise PayloadError("snapshot_in_future")
    return moment


def _parse_item(raw: object, index: int) -> SnapshotItem:
    if not isinstance(raw, dict):
        raise PayloadError("invalid_item", index)
    sku = raw.get("sku")
    if not isinstance(sku, str) or not sku.strip() or len(sku.strip()) > services.SKU_MAX_LENGTH:
        raise PayloadError("invalid_sku", index)
    on_hand = raw.get("onHand")
    if isinstance(on_hand, float) and on_hand.is_integer():
        on_hand = int(on_hand)
    # bool is an int subclass — `true` is not a stock count.
    if isinstance(on_hand, bool) or not isinstance(on_hand, int):
        raise PayloadError("invalid_on_hand", index)
    price: Decimal | None = None
    raw_price = raw.get("priceRs")
    if raw_price is not None:
        if isinstance(raw_price, bool) or not isinstance(raw_price, int | float | str):
            raise PayloadError("invalid_price", index)
        try:
            price = Decimal(str(raw_price))
        except InvalidOperation as exc:
            raise PayloadError("invalid_price", index) from exc
        if not price.is_finite() or price < 0:
            raise PayloadError("invalid_price", index)
        price = price.quantize(Decimal("0.01"))
    return SnapshotItem(sku=sku.strip(), on_hand=on_hand, price=price)


def _parse_snapshot(payload: dict[str, Any]) -> tuple[datetime, list[SnapshotItem]]:
    snapshot_at = _parse_snapshot_at(payload.get("snapshotAt"))
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise PayloadError("invalid_items")
    items = [_parse_item(raw, index) for index, raw in enumerate(raw_items)]
    seen: set[str] = set()
    for index, item in enumerate(items):
        if item.sku in seen:
            # Two counts for one SKU: refusing is the only non-guessing answer.
            raise PayloadError("duplicate_sku", index)
        seen.add(item.sku)
    return snapshot_at, items


@pos_endpoint("GET")
def ping(request: HttpRequest) -> HttpResponse:
    return json_response({"ok": True})


@pos_endpoint("POST")
def stock(request: HttpRequest) -> HttpResponse:
    """POST /api/pos/sync/stock/ — apply a stock snapshot.

    The whole request is validated before anything is applied, so a bad
    item never leaves a half-applied snapshot.
    """
    try:
        snapshot_at, items = _parse_snapshot(_read_json_object(request))
    except PayloadError as exc:
        return exc.response()

    result = services.apply_snapshot(snapshot_at=snapshot_at, items=items)
    body: dict[str, Any] = {
        "applied": result.applied,
        "unchanged": result.unchanged,
        "unmapped": result.unmapped,
        "oversold": result.oversold,
    }
    if result.stale:
        # A late retry of an older snapshot: acknowledged (so the POS stops
        # retrying) but not applied.
        body["stale"] = True
    return json_response(body)


@pos_endpoint("GET")
def web_orders(request: HttpRequest) -> HttpResponse:
    """GET /api/pos/sync/web-orders/ — confirmed web orders the POS has not
    yet recorded. Never includes customer names, phones or addresses."""
    orders = services.web_orders_payload()
    for order in orders:
        confirmed = order["paidAt"]
        order["paidAt"] = confirmed.astimezone(UTC).strftime(_TIME_FORMAT) if confirmed else None
    return json_response({"orders": orders})


@pos_endpoint("POST")
def ack_order(request: HttpRequest, order_id: int) -> HttpResponse:
    """POST /api/pos/sync/web-orders/<id>/ack/ — idempotent per sale number."""
    try:
        payload = _read_json_object(request)
    except PayloadError as exc:
        return exc.response()
    sale_number = payload.get("posSaleNumber")
    if (
        not isinstance(sale_number, str)
        or not sale_number.strip()
        or len(sale_number.strip()) > SALE_NUMBER_MAX_LENGTH
    ):
        return error_response(400, "invalid_pos_sale_number")

    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return error_response(404, "not_found")
    try:
        ack, already = services.acknowledge(order=order, pos_sale_number=sale_number.strip())
    except AckConflictError as exc:
        return json_response(
            {"error": "already_acked_differently", "posSaleNumber": exc.existing}, status=409
        )
    except OrderNotAwaitingAckError:
        return json_response(
            {"error": "order_not_awaiting_ack", "status": order.status}, status=409
        )
    return json_response(
        {
            "ok": True,
            "orderId": order.pk,
            "posSaleNumber": ack.pos_sale_number,
            "alreadyAcked": already,
        }
    )
