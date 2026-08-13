"""Order domain model (requirements §22, §24, roadmap Stage 8) — the
transactional core. See ``orders/services.py::create_order`` for the
creation transaction; this module is fields only.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from catalog.models import ProductVariant
from core.models import TimeStampedModel
from customers.models import Customer
from payments.models import PaymentStatus


class Order(TimeStampedModel):
    """Every customer/delivery detail below is a **snapshot**, taken at
    order creation — never read live through ``customer``. A customer
    moving house, or changing their name, must not rewrite where last
    month's order was delivered (§24).

    ``customer`` is ``on_delete=SET_NULL`` for the same reason
    ``OrderItem.variant`` is: every value a template needs is already on
    this row, so a deleted ``Customer`` can't corrupt order history.
    """

    class Status(models.TextChoices):
        PENDING_CONFIRMATION = "pending_confirmation", "Pending Confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        READY_TO_DISPATCH = "ready_to_dispatch", "Ready to Dispatch"
        DISPATCHED = "dispatched", "Dispatched"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        FAILED_DELIVERY = "failed_delivery", "Failed Delivery"
        RETURNED = "returned", "Returned"
        EXPIRED = "expired", "Expired"

    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, related_name="orders"
    )

    # Snapshotted customer details.
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=20)
    customer_whatsapp_number = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True, default="")

    # Snapshotted delivery details.
    delivery_address = models.TextField()
    delivery_city = models.CharField(max_length=100)
    delivery_postal_code = models.CharField(max_length=20, blank=True, default="")
    delivery_instructions = models.TextField(blank=True, default="")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.PENDING_CONFIRMATION
    )

    # Payment (§28) — schema-ready, unused in MVP. payment_method is the
    # one field with a real default (never actually null in practice);
    # §24 lists it among "all nullable" fields, which contradicts §28's
    # own "defaults to whatsapp_pending" — resolved in favour of §28's
    # more specific instruction. Recorded as a Proposed spec amendment in
    # state.md, not silently decided. payment_provider/refund_status are
    # plain strings, not TextChoices — adding a new provider (JazzCash,
    # Easypaisa, ...) must never need a migration.
    payment_method = models.CharField(max_length=32, default="whatsapp_pending")
    payment_status = models.CharField(
        max_length=32, choices=PaymentStatus.choices, null=True, blank=True
    )
    payment_provider = models.CharField(max_length=64, null=True, blank=True)
    transaction_id = models.CharField(max_length=128, null=True, blank=True)
    payment_reference = models.CharField(max_length=128, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    refund_status = models.CharField(max_length=32, null=True, blank=True)

    customer_notes = models.TextField(blank=True, default="")
    merchant_notes = models.TextField(blank=True, default="")
    tracking_number = models.CharField(max_length=100, blank=True, default="")
    courier_name = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.order_number


class OrderItem(TimeStampedModel):
    """``product_name``, ``variant_label``, ``sku``, ``unit_price``, and
    ``line_total`` are immutable snapshots, copied once at creation.
    **Every display value comes from these fields — never from
    ``.variant.price`` or ``.variant.product.name``.** ``variant`` is a
    reporting convenience FK only; nothing renders through it. Enforced
    by an automated test that greps every order template for those two
    exact patterns (roadmap Stage 8 gate 2), not just this docstring.

    ``variant`` is ``on_delete=SET_NULL`` — the roadmap's own named trap:
    ``CASCADE`` here would let deleting a product destroy order history.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )

    product_name = models.CharField(max_length=200)
    variant_label = models.CharField(max_length=255)
    sku = models.CharField(max_length=64)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name} ({self.order.order_number})"


class OrderStatusEvent(TimeStampedModel):
    """One row per status transition (§23) — both the merchant audit trail
    and the customer-facing timeline (§25, Stage 11). ``orders.services.
    create_order()`` writes the first row itself (``from_status=""`` ->
    ``PENDING_CONFIRMATION``, ``actor=None``) so the timeline has something
    to show from the moment an order exists, not only from its first
    merchant-driven change. ``orders.state_machine.transition_status()``
    writes every row after that.

    ``actor`` is nullable + ``SET_NULL`` (a deleted user account must not
    erase the timeline) and blank for the creation event specifically,
    since no merchant acted — the customer's own checkout did.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_events")
    from_status = models.CharField(max_length=32, blank=True, default="")
    to_status = models.CharField(max_length=32, choices=Order.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_status_events",
    )
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.order.order_number}: {self.from_status or '(new)'} -> {self.to_status}"


class OrderEditEvent(TimeStampedModel):
    """Audit row for one order-editing action (§23's editing rule) —
    quantity change, line removed, line added, or a line-price override.
    ``before``/``after`` are JSON rather than typed columns because the
    shape genuinely differs per ``edit_type`` (quantity+price for a
    quantity change; a full item snapshot for add/remove, where one side
    is legitimately absent — ``null=True`` on both fields, not an empty
    dict, so "there was nothing here yet" round-trips honestly rather than
    being indistinguishable from "the value was empty").

    No FK to ``OrderItem``: a remove-line event must survive the row it
    describes being deleted, so ``description`` (the product name and SKU)
    is what keeps the row identifiable on its own.

    There is no ``audit.AuditLog`` app yet — §33's general-purpose audit
    trail is P1 (roadmap Stage 15). This model is scoped narrowly to order
    edits, the same way ``inventory.InventoryAdjustment`` is scoped to
    stock changes rather than waiting on a general audit app that doesn't
    exist yet.
    """

    class EditType(models.TextChoices):
        QUANTITY_CHANGED = "quantity_changed", "Quantity changed"
        LINE_ADDED = "line_added", "Line added"
        LINE_REMOVED = "line_removed", "Line removed"
        PRICE_OVERRIDDEN = "price_overridden", "Price overridden"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="edit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_edit_events",
    )
    edit_type = models.CharField(max_length=32, choices=EditType.choices)
    description = models.CharField(max_length=255)
    before = models.JSONField(null=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order.order_number}: {self.edit_type} — {self.description}"
