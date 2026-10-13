from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from catalog.models import ProductVariant
from core.models import TimeStampedModel


class PosProduct(TimeStampedModel):
    """One product in the store POS — including watches, sunglasses and
    anything else never sold online.

    The *mapping* to the website is not stored here: it is
    ``ProductVariant.pos_sku`` (unique when set), so a POS SKU can be linked
    to at most one variant and a variant to at most one POS SKU by
    construction. A ``PosProduct`` is "mapped" iff some variant carries its
    ``sku``.
    """

    sku = models.CharField(max_length=128, unique=True)
    brand = models.CharField(max_length=150, blank=True, default="")
    name = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(max_length=150, blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Deliberately kept online-less (a watch). Survives CSV re-uploads.
    not_online = models.BooleanField(default=False)

    class Meta:
        ordering = ["brand", "name", "sku"]
        permissions = [
            # Not granted to the Staff group (accounts/permissions.py only
            # lists the catalog app), so only the Owner/superuser holds it.
            ("manage_pos_mapping", "Can manage the POS mapping and see POS sync status"),
        ]

    def __str__(self) -> str:
        return self.sku


class PosMappingEvent(TimeStampedModel):
    """Append-only audit trail of every mapping change (who / when / what).

    ``variant`` is ``SET_NULL`` with ``variant_sku`` snapshotted beside it,
    and ``actor`` is ``SET_NULL``: deleting a variant or a user must not
    delete the history of what was done.
    """

    class Action(models.TextChoices):
        MAPPED = "mapped", "Mapped to a variant"
        UNMAPPED = "unmapped", "Mapping removed"
        MARKED_NOT_ONLINE = "marked_not_online", "Marked not sold online"
        MARKED_ONLINE = "marked_online", "Marked sold online"
        CSV_IMPORT = "csv_import", "POS product CSV imported"
        ORDERS_CUTOFF = "orders_cutoff", "Web-order cutoff changed"

    action = models.CharField(max_length=24, choices=Action.choices)
    pos_sku = models.CharField(max_length=128, blank=True, default="")
    variant = models.ForeignKey(
        ProductVariant, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    variant_sku = models.CharField(max_length=64, blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.action} {self.pos_sku}"


class PosSyncState(models.Model):
    """Singleton (pk=1): what the sync last did, plus the order cutoff.

    ``orders_since`` is the safety rail the stock formula needs: only web
    orders *confirmed on or after* this moment count as "not yet recorded in
    the POS". Without it, every historical confirmed/delivered order — none
    of which will ever be acknowledged — would be subtracted from the very
    first snapshot's on-hand and zero out stock. It defaults to the moment
    the state row is first created (go-live) and is editable by the admin.
    """

    orders_since = models.DateTimeField(default=timezone.now)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)
    last_applied_at = models.DateTimeField(null=True, blank=True)
    # {"applied": n, "unchanged": n, "unmapped": [...], "oversold": [...]}
    last_result = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return "POS sync state"


class PosOrderAck(models.Model):
    """ "This web order has been recorded in the POS as sale ``pos_sale_number``."

    A separate table (not a column on ``orders.Order``) so the integration
    adds a table instead of altering one of the shop's busiest. One row per
    order (OneToOne) makes acknowledgement idempotent by construction.
    """

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="pos_ack")
    pos_sale_number = models.CharField(max_length=64)
    acked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"order {self.order_id} -> {self.pos_sale_number}"
