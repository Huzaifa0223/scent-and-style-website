"""Order editing (§23, roadmap Stage 10) — the four actions a merchant may
take while an order is ``Pending Confirmation`` or ``Confirmed``: change a
line's quantity, remove a line, add a line, or override a line's unit
price. Each function locks the order row, checks
``orders.status.EDITABLE_STATUSES``, applies the edit, recalculates
``subtotal``/``delivery_charge``/``total`` the same way checkout itself
does, and writes one ``OrderEditEvent`` capturing before/after.

**Every stock-affecting edit goes through ``inventory.services`` — this
module never creates, updates, or deletes a ``StockReservation`` or
touches ``ProductVariant.stock_quantity`` directly.** Which
``inventory.services`` function applies depends on whether the order is
still ``Pending Confirmation`` (stock is only *reserved*, never
decremented — ``reserve()``/``release_reserved()``) or already
``Confirmed`` (stock was already permanently decremented by
``commit_reservation()`` at the Confirmed transition, so there is no
reservation left to adjust — ``consume()``/``restore()`` touch
``stock_quantity`` directly instead). A quantity-up edit reserves/consumes
the delta; a quantity-down edit releases/restores the delta — never the
whole new-vs-old quantity, so a partial edit can't accidentally over- or
under-adjust stock relative to what's already held.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from catalog.models import ProductVariant
from inventory import services as inventory_services
from inventory.models import InventoryAdjustment
from shipping.calculators import get_delivery_calculator

from .models import Order, OrderEditEvent, OrderItem
from .status import EDITABLE_STATUSES, Status


class OrderNotEditableError(Exception):
    def __init__(self, order: Order) -> None:
        self.order = order
        super().__init__(f"Order {order.order_number} is not editable in status {order.status!r}.")


class LineEditError(Exception):
    """A well-formed edit request rejected by a business rule — a
    duplicate variant on add-line, a line that doesn't belong to this
    order, a line whose variant no longer exists, or the last remaining
    line on remove. Distinct from ``inventory.services.
    InsufficientStockError``, which callers should catch separately."""


def _lock_editable_order(order: Order) -> Order:
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status not in EDITABLE_STATUSES:
        raise OrderNotEditableError(locked)
    return locked


def _recalculate_totals(order: Order) -> None:
    subtotal = sum((item.line_total for item in order.items.all()), Decimal("0.00"))
    delivery_charge = get_delivery_calculator().calculate(
        subtotal=subtotal, city=order.delivery_city
    )
    order.subtotal = subtotal
    order.delivery_charge = delivery_charge
    order.total = subtotal + delivery_charge - order.discount
    order.save(update_fields=["subtotal", "delivery_charge", "total", "updated_at"])


def _item_snapshot(item: OrderItem) -> dict[str, object]:
    return {
        "product_name": item.product_name,
        "sku": item.sku,
        "variant_label": item.variant_label,
        "unit_price": item.unit_price,
        "quantity": item.quantity,
        "line_total": item.line_total,
    }


@transaction.atomic
def change_line_quantity(
    *, order: Order, item: OrderItem, new_quantity: int, actor: User | None
) -> OrderEditEvent | None:
    """Returns ``None`` (writes nothing) if ``new_quantity`` equals the
    current quantity — a no-op resubmission isn't an edit."""
    if new_quantity <= 0:
        raise LineEditError("Quantity must be at least 1 — remove the line instead.")

    locked_order = _lock_editable_order(order)
    if item.order_id != locked_order.pk:
        raise LineEditError("That line does not belong to this order.")
    if item.variant_id is None:
        raise LineEditError("This line's product no longer exists — its quantity can't change.")

    delta = new_quantity - item.quantity
    if delta == 0:
        return None

    before = {
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
    }

    if locked_order.status == Status.PENDING_CONFIRMATION:
        if delta > 0:
            inventory_services.reserve(
                variant_id=item.variant_id, quantity=delta, order=locked_order
            )
        else:
            inventory_services.release_reserved(
                variant_id=item.variant_id, order=locked_order, quantity=-delta
            )
    else:  # Status.CONFIRMED
        if delta > 0:
            inventory_services.consume(
                variant_id=item.variant_id,
                quantity=delta,
                reason=InventoryAdjustment.Reason.ORDER_EDITED,
                actor=actor,
            )
        else:
            inventory_services.restore(
                variant_id=item.variant_id,
                quantity=-delta,
                reason=InventoryAdjustment.Reason.ORDER_EDITED,
                actor=actor,
            )

    item.quantity = new_quantity
    item.line_total = item.unit_price * new_quantity
    item.save(update_fields=["quantity", "line_total", "updated_at"])
    after = {
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
    }

    _recalculate_totals(locked_order)
    return OrderEditEvent.objects.create(
        order=locked_order,
        actor=actor,
        edit_type=OrderEditEvent.EditType.QUANTITY_CHANGED,
        description=f"{item.product_name} ({item.sku})",
        before=before,
        after=after,
    )


@transaction.atomic
def remove_line(*, order: Order, item: OrderItem, actor: User | None) -> OrderEditEvent:
    locked_order = _lock_editable_order(order)
    if item.order_id != locked_order.pk:
        raise LineEditError("That line does not belong to this order.")
    if locked_order.items.count() <= 1:
        raise LineEditError(
            "An order must have at least one line — cancel the order instead of removing its "
            "last item."
        )

    if item.variant_id is not None:
        if locked_order.status == Status.PENDING_CONFIRMATION:
            inventory_services.release_reserved(
                variant_id=item.variant_id, order=locked_order, quantity=item.quantity
            )
        else:  # Status.CONFIRMED
            inventory_services.restore(
                variant_id=item.variant_id,
                quantity=item.quantity,
                reason=InventoryAdjustment.Reason.ORDER_EDITED,
                actor=actor,
            )

    before = _item_snapshot(item)
    description = f"{item.product_name} ({item.sku})"
    item.delete()

    _recalculate_totals(locked_order)
    return OrderEditEvent.objects.create(
        order=locked_order,
        actor=actor,
        edit_type=OrderEditEvent.EditType.LINE_REMOVED,
        description=description,
        before=before,
        after=None,
    )


@transaction.atomic
def add_line(
    *, order: Order, variant: ProductVariant, quantity: int, actor: User | None
) -> OrderEditEvent:
    if quantity <= 0:
        raise LineEditError("Quantity must be at least 1.")

    locked_order = _lock_editable_order(order)
    if locked_order.items.filter(variant=variant).exists():
        raise LineEditError(
            f"{variant.sku} is already a line on this order — change its quantity instead."
        )
    if not variant.is_active:
        raise LineEditError(f"{variant.sku} is not active and can't be added to an order.")

    if locked_order.status == Status.PENDING_CONFIRMATION:
        inventory_services.reserve(variant_id=variant.pk, quantity=quantity, order=locked_order)
    else:  # Status.CONFIRMED
        inventory_services.consume(
            variant_id=variant.pk,
            quantity=quantity,
            reason=InventoryAdjustment.Reason.ORDER_EDITED,
            actor=actor,
        )

    item = OrderItem.objects.create(
        order=locked_order,
        variant=variant,
        product_name=variant.product.name,
        variant_label=variant.display_label,
        sku=variant.sku,
        unit_price=variant.price,
        quantity=quantity,
        line_total=variant.price * quantity,
    )

    _recalculate_totals(locked_order)
    return OrderEditEvent.objects.create(
        order=locked_order,
        actor=actor,
        edit_type=OrderEditEvent.EditType.LINE_ADDED,
        description=f"{item.product_name} ({item.sku})",
        before=None,
        after=_item_snapshot(item),
    )


@transaction.atomic
def override_line_price(
    *, order: Order, item: OrderItem, new_unit_price: Decimal, actor: User | None
) -> OrderEditEvent:
    if new_unit_price < 0:
        raise LineEditError("Unit price cannot be negative.")

    locked_order = _lock_editable_order(order)
    if item.order_id != locked_order.pk:
        raise LineEditError("That line does not belong to this order.")

    before = {"unit_price": item.unit_price, "line_total": item.line_total}
    item.unit_price = new_unit_price
    item.line_total = new_unit_price * item.quantity
    item.save(update_fields=["unit_price", "line_total", "updated_at"])
    after = {"unit_price": item.unit_price, "line_total": item.line_total}

    _recalculate_totals(locked_order)
    return OrderEditEvent.objects.create(
        order=locked_order,
        actor=actor,
        edit_type=OrderEditEvent.EditType.PRICE_OVERRIDDEN,
        description=f"{item.product_name} ({item.sku})",
        before=before,
        after=after,
    )
