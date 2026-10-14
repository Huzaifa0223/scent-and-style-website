"""POS sync domain logic. Views stay thin; everything that decides or
changes something lives here.

THE STOCK FORMULA (one place, deliberately boring). Two modes, chosen by
``settings.POS_SYNC_SUBTRACT_WEB_ORDERS``:

  read-only (default, False) — web orders are NOT subtracted; staff ring them
  up at the till so the POS on-hand already drops:

    available_quantity = onHand
                         - (units in active cart/pending-order reservations)

  subtracting (True) — for when web orders are recorded in the POS and
  acknowledged:

    available_quantity = onHand
                         - (units in web orders awaiting POS acknowledgement)
                         - (units in active cart/pending-order reservations)

The rest of this docstring describes the subtracting mode; read-only is the
same with the awaiting-acknowledgement term fixed at zero (and so no
"oversold").

``available_quantity`` is already ``stock_quantity - active reservations``
(``ProductVariantQuerySet.with_available_quantity``). So the sync only has to
make ``stock_quantity = max(onHand - unacknowledged, 0)`` and the existing
reservation logic subtracts reservations. "Awaiting acknowledgement" means:
status Confirmed or later (stock already decremented by the shop) and not
Cancelled/Returned/Expired, confirmed on/after ``PosSyncState.orders_since``,
and with no ``PosOrderAck``.

The sync *sets* ``stock_quantity`` absolutely each time rather than applying
deltas, so it self-heals: confirming an order decrements the same number the
next snapshot would compute, and acknowledging one needs no recompute (the
POS's on-hand drops by the same units that stop being subtracted).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, F, OuterRef, QuerySet, Subquery, Sum
from django.utils import timezone

from catalog.models import ProductVariant
from inventory import services as inventory_services
from orders.models import Order, OrderItem, OrderStatusEvent

from . import matching
from .config import (
    BULK_CONFIRM_MIN_SCORE,
    MARK_RECORDED_MAX_REASON_LENGTH,
    MARK_RECORDED_MIN_REASON_LENGTH,
    NOT_ONLINE_CATEGORY_KEYWORDS,
    SNAPSHOT_LOCK_KEY,
)
from .matching import VariantCandidate
from .models import PosMappingEvent, PosOrderAck, PosProduct, PosSyncState

logger = logging.getLogger(__name__)

Status = Order.Status

# Statuses in which the shop has already decremented stock for the order and
# has not given it back. Pending Confirmation is covered by reservations;
# Cancelled/Returned/Expired restored (or never took) the stock.
AWAITING_ACK_STATUSES: Final[frozenset[str]] = frozenset(
    {
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.READY_TO_DISPATCH,
        Status.DISPATCHED,
        Status.OUT_FOR_DELIVERY,
        Status.DELIVERED,
        Status.FAILED_DELIVERY,
    }
)

_TRUE_WORDS: Final = frozenset({"1", "true", "yes", "y", "active", "t"})
_FALSE_WORDS: Final = frozenset({"0", "false", "no", "n", "inactive", "f"})
_CSV_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")
SKU_MAX_LENGTH: Final[int] = 128


class MappingError(Exception):
    """A mapping change that cannot be made; the message is shown to the admin."""


# --- state -------------------------------------------------------------------


def subtract_web_orders_enabled() -> bool:
    """``settings.POS_SYNC_SUBTRACT_WEB_ORDERS`` — see the module docstring.
    Read at call time so it can be switched without touching code."""
    return bool(getattr(settings, "POS_SYNC_SUBTRACT_WEB_ORDERS", False))


def get_state() -> PosSyncState:
    state, _ = PosSyncState.objects.get_or_create(pk=1)
    return state


def awaiting_ack_orders() -> QuerySet[Order]:
    """Web orders the POS still has to record (see module docstring)."""
    since = get_state().orders_since
    confirmed_in_window = OrderStatusEvent.objects.filter(
        order=OuterRef("pk"), to_status=Status.CONFIRMED, created_at__gte=since
    )
    return Order.objects.filter(status__in=AWAITING_ACK_STATUSES, pos_ack__isnull=True).filter(
        Exists(confirmed_in_window)
    )


def units_awaiting_ack(variant_id: int) -> int:
    total = OrderItem.objects.filter(
        variant_id=variant_id, order__in=awaiting_ack_orders()
    ).aggregate(total=Sum("quantity"))["total"]
    return int(total or 0)


def set_orders_since(*, moment: datetime, actor: User | None) -> None:
    state = get_state()
    previous = state.orders_since
    state.orders_since = moment
    state.save(update_fields=["orders_since"])
    PosMappingEvent.objects.create(
        action=PosMappingEvent.Action.ORDERS_CUTOFF,
        actor=actor,
        note=f"Web-order cutoff {previous:%Y-%m-%d %H:%M} -> {moment:%Y-%m-%d %H:%M}",
    )


# --- POS product CSV ---------------------------------------------------------


@dataclass
class CsvImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def rows_ok(self) -> int:
        return self.created + self.updated


def _parse_bool(raw: str) -> bool | None:
    value = raw.strip().lower()
    if value in _TRUE_WORDS:
        return True
    if value in _FALSE_WORDS:
        return False
    return None


def _parse_price(raw: str) -> Decimal | None:
    cleaned = re.sub(r"(?i)\brs\.?|pkr|,|\s", "", raw)
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"price {raw!r} is not a number") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"price {raw!r} must be zero or more")
    return value.quantize(Decimal("0.01"))


def import_pos_csv(raw: bytes, *, actor: User | None) -> CsvImportResult:
    """Upsert ``PosProduct`` rows from ``sku,brand,name,category,price_rs,active``.

    Valid rows are applied and bad rows reported (with their line number),
    so one typo in a thousand-row export does not block the other 999. A
    row never touches ``not_online`` or ``last_seen_at`` — those belong to
    the admin and to the stock sync respectively.
    """
    result = CsvImportResult()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        result.errors.append("File is not UTF-8 text.")
        return result

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        result.errors.append("File is empty.")
        return result
    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "sku" not in columns:
        result.errors.append("Missing required column: sku.")
        return result

    def cell(row: dict[str, str], key: str) -> str | None:
        source = columns.get(key)
        if source is None:
            return None
        return (row.get(source) or "").strip()

    parsed: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(reader, start=2):
        sku = cell(row, "sku") or ""
        if not sku:
            if any((value or "").strip() for value in row.values()):
                result.errors.append(f"Line {line_number}: sku is empty.")
            continue
        if len(sku) > SKU_MAX_LENGTH:
            result.errors.append(f"Line {line_number}: sku is longer than {SKU_MAX_LENGTH}.")
            continue
        if sku in parsed:
            result.errors.append(f"Line {line_number}: duplicate sku {sku!r}; first one kept.")
            continue
        values: dict[str, Any] = {}
        try:
            for key, max_length in (("brand", 150), ("name", 255), ("category", 150)):
                value = cell(row, key)
                if value is None:
                    continue
                if len(value) > max_length:
                    raise ValueError(f"{key} is longer than {max_length}")
                values[key] = value
            price_raw = cell(row, "price_rs")
            if price_raw is not None:
                values["price"] = _parse_price(price_raw)
            active_raw = cell(row, "active")
            if active_raw:
                active = _parse_bool(active_raw)
                if active is None:
                    raise ValueError(f"active {active_raw!r} is not yes/no")
                values["active"] = active
        except ValueError as exc:
            result.errors.append(f"Line {line_number}: {exc}.")
            continue
        parsed[sku] = values

    with transaction.atomic():
        existing = PosProduct.objects.in_bulk(list(parsed), field_name="sku")
        to_create: list[PosProduct] = []
        to_update: list[PosProduct] = []
        now = timezone.now()
        for sku, values in parsed.items():
            product = existing.get(sku)
            if product is None:
                to_create.append(PosProduct(sku=sku, **values))
                continue
            for key, value in values.items():
                setattr(product, key, value)
            product.updated_at = now
            to_update.append(product)
        PosProduct.objects.bulk_create(to_create)
        update_fields = ["brand", "name", "category", "price", "active", "updated_at"]
        PosProduct.objects.bulk_update(to_update, update_fields)
        result.created, result.updated = len(to_create), len(to_update)
        PosMappingEvent.objects.create(
            action=PosMappingEvent.Action.CSV_IMPORT,
            actor=actor,
            note=(
                f"{result.created} created, {result.updated} updated, "
                f"{len(result.errors)} row error(s)"
            ),
        )
    return result


def csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_CSV_FORMULA_PREFIXES) else text


# --- mapping -----------------------------------------------------------------


def unmapped_candidates() -> list[VariantCandidate]:
    """Every variant without a POS SKU, as plain values for ``matching``."""
    variants = (
        ProductVariant.objects.filter(pos_sku__isnull=True)
        .select_related("product", "product__brand")
        .prefetch_related("variant_attribute_values__value")
        .order_by("product__name", "position", "id")
    )
    return [
        VariantCandidate(
            variant_id=variant.pk,
            brand=variant.product.brand.name if variant.product.brand else "",
            product_name=variant.product.name,
            label=variant.display_label,
            sku=variant.sku,
            price=variant.price,
        )
        for variant in variants
    ]


def _audit(
    action: PosMappingEvent.Action,
    *,
    pos_sku: str,
    actor: User | None,
    variant: ProductVariant | None = None,
    note: str = "",
) -> None:
    PosMappingEvent.objects.create(
        action=action,
        pos_sku=pos_sku,
        variant=variant,
        variant_sku=variant.sku if variant else "",
        actor=actor,
        note=note,
    )


@transaction.atomic
def confirm_mapping(
    *, pos_product: PosProduct, variant_id: int, actor: User | None, note: str = ""
) -> ProductVariant:
    """Link ``pos_product`` to a variant. A human decision, never automatic.

    ``note`` is appended to the audit row (the bulk review uses it so the
    history shows which links came from a bulk confirmation)."""
    try:
        variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    except ProductVariant.DoesNotExist as exc:
        raise MappingError("That variant no longer exists.") from exc
    if variant.pos_sku == pos_product.sku:
        return variant
    if variant.pos_sku:
        raise MappingError(f"{variant.sku} is already mapped to POS SKU {variant.pos_sku}.")
    try:
        with transaction.atomic():
            variant.pos_sku = pos_product.sku
            variant.save(update_fields=["pos_sku", "updated_at"])
    except IntegrityError as exc:
        raise MappingError(
            f"POS SKU {pos_product.sku} is already mapped to another variant."
        ) from exc
    if pos_product.not_online:
        pos_product.not_online = False
        pos_product.save(update_fields=["not_online", "updated_at"])
        note = f"{note} Cleared 'not sold online'.".strip()
    _audit(
        PosMappingEvent.Action.MAPPED,
        pos_sku=pos_product.sku,
        actor=actor,
        variant=variant,
        note=note,
    )
    return variant


@transaction.atomic
def remove_mapping(*, pos_sku: str, actor: User | None) -> None:
    variant = ProductVariant.objects.select_for_update().filter(pos_sku=pos_sku).first()
    if variant is None:
        raise MappingError(f"POS SKU {pos_sku} is not mapped.")
    variant.pos_sku = None
    variant.save(update_fields=["pos_sku", "updated_at"])
    _audit(PosMappingEvent.Action.UNMAPPED, pos_sku=pos_sku, actor=actor, variant=variant)


@transaction.atomic
def set_not_online(*, pos_product: PosProduct, value: bool, actor: User | None) -> None:
    if value and ProductVariant.objects.filter(pos_sku=pos_product.sku).exists():
        raise MappingError("Remove the mapping first, then mark it as not sold online.")
    if pos_product.not_online == value:
        return
    pos_product.not_online = value
    pos_product.save(update_fields=["not_online", "updated_at"])
    _audit(
        PosMappingEvent.Action.MARKED_NOT_ONLINE if value else PosMappingEvent.Action.MARKED_ONLINE,
        pos_sku=pos_product.sku,
        actor=actor,
    )


@dataclass(frozen=True)
class BulkProposal:
    """One POS product with the single website variant it very probably is."""

    pos_product: PosProduct
    display_name: str  # POS name with a repeated brand stripped
    suggestion: matching.Suggestion


@dataclass(frozen=True)
class BulkProposals:
    proposals: list[BulkProposal]
    ambiguous: int  # rows left out: tie, or the same variant proposed twice


def bulk_match_proposals(min_score: float = BULK_CONFIRM_MIN_SCORE) -> BulkProposals:
    """Unmapped, sold-online POS products whose best suggestion scores at
    least ``min_score`` — the list behind "Review and confirm all matches".

    Deliberately conservative, because the owner ticks rows from a long
    list: a POS row is left out when its best two candidates both reach the
    threshold (the tie would be broken arbitrarily), when its size or
    gift-set status disagrees with the candidate, when either side's size
    is unknown (a 50 ml bottle must not be confirmed against a variant
    whose size we cannot read), or when another POS row
    proposes the same variant (at most one can be right). Everything left
    out stays on the normal page for a one-by-one decision.
    """
    candidates = unmapped_candidates()
    pos_products = list(
        PosProduct.objects.filter(not_online=False)
        .exclude(sku__in=ProductVariant.objects.filter(pos_sku__isnull=False).values("pos_sku"))
        .order_by("brand", "name", "sku")
    )
    ambiguous = 0
    picked: list[BulkProposal] = []
    for pos_product in pos_products:
        ranked = matching.suggest(
            pos_brand=pos_product.brand,
            pos_name=pos_product.name,
            pos_sku=pos_product.sku,
            candidates=candidates,
            limit=2,
            min_score=min_score,
        )
        if not ranked:
            continue
        if len(ranked) > 1 or ranked[0].size_mismatch or ranked[0].size_unknown:
            ambiguous += 1
            continue
        picked.append(
            BulkProposal(
                pos_product=pos_product,
                display_name=matching.strip_leading_brand(pos_product.brand, pos_product.name),
                suggestion=ranked[0],
            )
        )
    by_variant = Counter(p.suggestion.candidate.variant_id for p in picked)
    kept = [p for p in picked if by_variant[p.suggestion.candidate.variant_id] == 1]
    return BulkProposals(proposals=kept, ambiguous=ambiguous + len(picked) - len(kept))


@dataclass
class BulkResult:
    done: int = 0
    errors: list[str] = field(default_factory=list)


def confirm_mappings(*, pairs: list[tuple[int, int]], actor: User | None) -> BulkResult:
    """Map each ``(pos_product_id, variant_id)`` the owner ticked.

    Each pair is its own transaction (``confirm_mapping``), so one stale row
    — a variant mapped meanwhile — is reported and skipped without undoing
    the rest."""
    result = BulkResult()
    products = PosProduct.objects.in_bulk([pos_id for pos_id, _ in pairs])
    for pos_id, variant_id in pairs:
        pos_product = products.get(pos_id)
        if pos_product is None:
            result.errors.append(f"POS product #{pos_id} no longer exists.")
            continue
        try:
            confirm_mapping(
                pos_product=pos_product,
                variant_id=variant_id,
                actor=actor,
                note="Bulk confirmation.",
            )
        except MappingError as exc:
            result.errors.append(f"{pos_product.sku}: {exc}")
        else:
            result.done += 1
    return result


def set_not_online_many(*, pos_ids: list[int], actor: User | None) -> BulkResult:
    """Mark every ticked POS product "not sold online"; a product that is
    already mapped is reported and skipped (``set_not_online`` refuses it)."""
    result = BulkResult()
    for pos_product in PosProduct.objects.filter(pk__in=pos_ids).order_by("sku"):
        try:
            set_not_online(pos_product=pos_product, value=True, actor=actor)
        except MappingError as exc:
            result.errors.append(f"{pos_product.sku}: {exc}")
        else:
            result.done += 1
    return result


def looks_not_sold_online(category: str) -> bool:
    """Whether a POS category reads like a watch, sunglasses or accessory —
    things this store sells at the till but not on the website."""
    lowered = category.casefold()
    return any(keyword in lowered for keyword in NOT_ONLINE_CATEGORY_KEYWORDS)


def price_mismatches() -> QuerySet[ProductVariant]:
    """Mapped variants whose last POS price differs from the website price —
    for a human to fix by hand. Nothing here ever writes ``price``."""
    return (
        ProductVariant.objects.filter(pos_sku__isnull=False, pos_price__isnull=False)
        .exclude(pos_price=F("price"))
        .select_related("product")
        .order_by("product__name", "position", "id")
    )


# --- stock snapshot ----------------------------------------------------------


@dataclass(frozen=True)
class SnapshotItem:
    sku: str
    on_hand: int
    price: Decimal | None


@dataclass(frozen=True)
class SnapshotResult:
    applied: int
    unchanged: int
    unmapped: list[str]
    oversold: list[dict[str, Any]]
    skipped: list[dict[str, Any]] = field(default_factory=list)
    stale: bool = False


@contextmanager
def _snapshot_lock() -> Iterator[None]:
    """Serialise whole snapshots with a session-level Postgres advisory lock.

    Per-variant work runs in short transactions of its own (so POS sync
    never holds many variant row locks at once, and cannot deadlock with
    an order confirmation that locks several). That alone would let a late
    retry interleave with a newer snapshot and win some SKUs, which is
    exactly what the staleness rule exists to prevent — hence this lock.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [SNAPSHOT_LOCK_KEY])
        try:
            yield
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [SNAPSHOT_LOCK_KEY])


@transaction.atomic
def _apply_variant(
    *, variant_id: int, on_hand: int, price: Decimal | None, note: str
) -> tuple[bool, int] | None:
    """Set one variant's stock from the POS count. Returns ``(changed,
    short)`` or ``None`` if the variant vanished.

    The variant row is locked *before* the awaiting-ack total is read, so a
    concurrent order confirmation (which decrements stock and changes the
    order's status in one transaction, under this same lock) is either
    fully visible here or fully after us — never half-counted.
    """
    try:
        variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
    except ProductVariant.DoesNotExist:
        return None
    # Read-only mode (the default): the POS on-hand is used as is. The web-order
    # subtraction, and with it the "oversold" figure, only exist in the other mode.
    awaiting = units_awaiting_ack(variant_id) if subtract_web_orders_enabled() else 0
    target = max(on_hand - awaiting, 0)
    short = max(awaiting - on_hand, 0)
    changed = variant.stock_quantity != target
    if changed:
        # adjust() re-locks (same transaction), writes the InventoryAdjustment
        # row, and is a no-op when the number is unchanged — so a movement
        # exists only when stock really moved.
        inventory_services.adjust(variant_id=variant_id, absolute_quantity=target, note=note)
    if price is not None and variant.pos_price != price:
        ProductVariant.objects.filter(pk=variant_id).update(
            pos_price=price, updated_at=timezone.now()
        )
    return changed, short


def apply_snapshot(
    *,
    snapshot_at: datetime,
    items: list[SnapshotItem],
    skipped: list[dict[str, Any]] | None = None,
) -> SnapshotResult:
    """Apply a POS stock snapshot. See the module docstring for the formula.

    ``skipped`` are items the API layer refused to apply (empty/duplicate SKU,
    unusable count…); they are only carried through into the result and the
    remembered last sync so the portal and the POS can see them.
    """
    skipped = skipped or []
    with _snapshot_lock():
        state = get_state()
        if state.last_snapshot_at is not None and snapshot_at < state.last_snapshot_at:
            logger.info(
                "Ignored stale POS snapshot %s (< %s).", snapshot_at, state.last_snapshot_at
            )
            return SnapshotResult(
                applied=0, unchanged=0, unmapped=[], oversold=[], skipped=skipped, stale=True
            )

        now = timezone.now()
        skus = [item.sku for item in items]
        by_sku = {v.pos_sku: v.pk for v in ProductVariant.objects.filter(pos_sku__in=skus)}
        known = PosProduct.objects.in_bulk(skus, field_name="sku")
        note_suffix = f" (snapshot {snapshot_at:%Y-%m-%d %H:%M})"

        applied = unchanged = 0
        unmapped: list[str] = []
        oversold: list[dict[str, Any]] = []
        for item in items:
            variant_id = by_sku.get(item.sku)
            outcome = None
            if variant_id is not None:
                note = f"POS sync: {item.on_hand} on hand{note_suffix}"[:500]
                outcome = _apply_variant(
                    variant_id=variant_id, on_hand=item.on_hand, price=item.price, note=note
                )
            if outcome is None:
                product = known.get(item.sku)
                if product is None or not product.not_online:
                    unmapped.append(item.sku)
                continue
            changed, short = outcome
            if changed:
                applied += 1
            else:
                unchanged += 1
            if short:
                oversold.append({"sku": item.sku, "short": short})

        _remember_pos_products(items, known=known, now=now)

        result = SnapshotResult(
            applied=applied,
            unchanged=unchanged,
            unmapped=unmapped,
            oversold=oversold,
            skipped=skipped,
        )
        state.last_snapshot_at = snapshot_at
        state.last_applied_at = now
        state.last_result = {
            "applied": applied,
            "unchanged": unchanged,
            "unmapped": unmapped,
            "oversold": oversold,
            "skipped": skipped,
        }
        state.save(update_fields=["last_snapshot_at", "last_applied_at", "last_result"])
        return result


def _remember_pos_products(
    items: list[SnapshotItem], *, known: dict[Any, PosProduct], now: datetime
) -> None:
    """Upsert ``PosProduct`` for every SKU the POS reported (mapped or not)
    so the admin sees what exists in the POS. Name/brand/category come from
    the CSV, never from a snapshot — the snapshot only has sku and price."""
    to_create: list[PosProduct] = []
    to_update: list[PosProduct] = []
    for item in items:
        product = known.get(item.sku)
        if product is None:
            to_create.append(PosProduct(sku=item.sku, price=item.price, last_seen_at=now))
            continue
        product.last_seen_at = now
        product.updated_at = now
        if item.price is not None:
            product.price = item.price
        to_update.append(product)
    PosProduct.objects.bulk_create(to_create)
    PosProduct.objects.bulk_update(to_update, ["last_seen_at", "price", "updated_at"])


# --- web orders --------------------------------------------------------------


def _rupees(amount: Decimal) -> int | float:
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def web_orders_payload() -> list[dict[str, Any]]:
    """Orders awaiting acknowledgement, oldest first, with **no** customer
    data: only id, number, when it was confirmed, and its lines."""
    latest_confirmation = (
        OrderStatusEvent.objects.filter(order=OuterRef("pk"), to_status=Status.CONFIRMED)
        .order_by("-created_at")
        .values("created_at")[:1]
    )
    orders = (
        awaiting_ack_orders()
        .annotate(confirmed_at=Subquery(latest_confirmation))
        .prefetch_related("items__variant")
        .order_by("confirmed_at", "pk")
    )
    payload: list[dict[str, Any]] = []
    for order in orders:
        lines: list[dict[str, Any]] = []
        unmapped_lines: list[dict[str, Any]] = []
        for item in order.items.all():
            pos_sku = item.variant.pos_sku if item.variant is not None else None
            line = {
                "posSku": pos_sku,
                "variantSku": item.sku,
                "name": item.product_name,
                "qty": item.quantity,
                "unitPriceRs": _rupees(item.unit_price),
            }
            (lines if pos_sku else unmapped_lines).append(line)
        payload.append(
            {
                "id": order.pk,
                "number": order.order_number,
                "paidAt": order.confirmed_at,
                "lines": lines,
                "unmappedLines": unmapped_lines,
            }
        )
    return payload


class AckConflictError(Exception):
    """Order already acknowledged with a different POS sale number."""

    def __init__(self, existing: str) -> None:
        super().__init__(existing)
        self.existing = existing


class OrderNotAwaitingAckError(Exception):
    """The order's status is not one the POS should be recording."""


@transaction.atomic
def acknowledge(*, order: Order, pos_sale_number: str) -> tuple[PosOrderAck, bool]:
    """Idempotent acknowledgement by the POS. Returns ``(ack, already_acked)``;
    raises ``AckConflictError`` if a *different* sale number was recorded by
    the POS before. A manual mark is provisional and is upgraded to the POS's
    real sale number."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    existing = PosOrderAck.objects.filter(order=locked).first()
    if existing is not None:
        if existing.source == PosOrderAck.Source.MANUAL:
            existing.pos_sale_number = pos_sale_number
            existing.source = PosOrderAck.Source.POS
            existing.save(update_fields=["pos_sale_number", "source"])
            return existing, False
        if existing.pos_sale_number != pos_sale_number:
            raise AckConflictError(existing.pos_sale_number)
        return existing, True
    if locked.status not in AWAITING_ACK_STATUSES:
        raise OrderNotAwaitingAckError(locked.status)
    return PosOrderAck.objects.create(order=locked, pos_sale_number=pos_sale_number), False


@transaction.atomic
def mark_recorded(*, order: Order, reason: str, actor: User | None) -> PosOrderAck:
    """Owner action: take one web order out of the awaiting-ack count without
    a POS acknowledgement. Needs a reason and is audited.

    Its units stop being subtracted at the **next** POS snapshot (the sync
    sets stock absolutely from the POS count, which it does not store
    between snapshots), so use it for orders the POS on-hand already
    reflects or will never record.
    """
    reason = reason.strip()
    if len(reason) < MARK_RECORDED_MIN_REASON_LENGTH:
        raise MappingError(
            f"Give a reason of at least {MARK_RECORDED_MIN_REASON_LENGTH} characters."
        )
    if len(reason) > MARK_RECORDED_MAX_REASON_LENGTH:
        raise MappingError(f"Keep the reason under {MARK_RECORDED_MAX_REASON_LENGTH} characters.")

    locked = Order.objects.select_for_update().get(pk=order.pk)
    if PosOrderAck.objects.filter(order=locked).exists():
        raise MappingError(f"Order {locked.order_number} is already recorded.")
    if locked.status not in AWAITING_ACK_STATUSES:
        raise MappingError(f"Order {locked.order_number} is not waiting for the POS.")

    ack = PosOrderAck.objects.create(
        order=locked,
        pos_sale_number="",
        source=PosOrderAck.Source.MANUAL,
        reason=reason,
        marked_by=actor,
    )
    PosMappingEvent.objects.create(
        action=PosMappingEvent.Action.ORDER_MARKED_RECORDED,
        actor=actor,
        note=f"{locked.order_number}: {reason}"[:500],
    )
    return ack
