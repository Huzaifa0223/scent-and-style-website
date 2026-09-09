from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from core.config import STORE_SETTINGS_CACHE_KEY
from core.models import TimeStampedModel


class DeliveryStrategy(models.TextChoices):
    """Which of shipping.calculators's three strategies
    shipping.calculators.get_delivery_calculator() builds (§27). Lives
    here rather than in shipping/models.py so shipping (a consumer of
    StoreSettings) depends on store, not the other way around."""

    FLAT_RATE = "flat_rate", "Flat rate"
    FREE_ABOVE_THRESHOLD = "free_above_threshold", "Free above a threshold"
    CITY_BASED = "city_based", "City-based"


class StoreSettings(TimeStampedModel):
    """Singleton row holding every merchant-configurable value (§40).

    Pinned to primary key 1 by both a database ``CheckConstraint`` and
    ``save()``, so there is no path — application code, admin, or a raw
    insert — that can produce a second row. Fields are added stage by stage
    as later work needs them (delivery, reservation TTL, notification
    templates, SEO defaults, social links); Stage 1 only needs identity,
    contact, currency, and timezone.
    """

    name = models.CharField(max_length=200, default="My Store")
    address = models.TextField(blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    contact_phone = models.CharField(max_length=20, blank=True, default="")
    whatsapp_number = models.CharField(max_length=20, blank=True, default="")
    currency = models.CharField(max_length=3, default="PKR")
    timezone = models.CharField(max_length=64, default="Asia/Karachi")
    # Hours a StockReservation lives before the sweeper releases it back to
    # available stock (§10.1). Merchant-configurable — how long a customer
    # gets before an uncontacted WhatsApp order stops locking inventory.
    reservation_ttl_hours = models.PositiveIntegerField(default=24)

    # Delivery (§27) — which strategy shipping.calculators.
    # get_delivery_calculator() builds, and every rate/threshold all three
    # strategies draw from. flat_delivery_rate serves both FLAT_RATE (the
    # charge, always) and FREE_ABOVE_THRESHOLD (the charge, waived above
    # free_delivery_threshold) — the requirement describes the free-above-
    # threshold strategy as literally "flat rate, waived above a subtotal",
    # not a second independent rate. free_delivery_threshold is also read
    # by CITY_BASED, optionally ("city-based rates can carry a free-
    # delivery threshold" — §27) — nullable because that strategy doesn't
    # require one.
    delivery_strategy = models.CharField(
        max_length=32, choices=DeliveryStrategy.choices, default=DeliveryStrategy.FLAT_RATE
    )
    flat_delivery_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    free_delivery_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    city_fallback_delivery_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # WhatsApp handoff (§21, §26). site_url is the deployment's own public
    # base URL ("https://mystore.pk") — genuinely merchant/deployment
    # -specific, so it lives here rather than being derived from
    # ALLOWED_HOSTS (a Django security setting, not meant for building
    # public-facing links) or hard-coded anywhere. Blank by default; the
    # tracking link is simply omitted from WhatsApp messages until it's
    # configured, rather than ever sending a broken or placeholder URL.
    site_url = models.URLField(blank=True, default="")
    # Storefront presentation toggle: whether Product.short_description
    # renders below the product name on cards and the detail page.
    # Merchant-controlled rather than hard-coded in the template because a
    # merchant without short descriptions written yet would otherwise see
    # empty gaps under every product name.
    show_short_description = models.BooleanField(default=True)
    # roadmap's WHATSAPP_MESSAGE_MAX_CHARS — an UNVERIFIED, deliberately
    # conservative placeholder (see notifications/whatsapp/message_builder.py's
    # module docstring and specs/state.md's Stage 9 entry). §21 requires
    # this to be measured empirically on real devices/clients before the
    # default is trusted; that measurement has not happened.
    whatsapp_message_max_chars = models.PositiveIntegerField(
        default=1000, validators=[MinValueValidator(200)]
    )
    # Status-update templates (§26), merchant-editable. Supported
    # placeholders: {customer_name}, {order_number}, {tracking_number},
    # {courier_name}, {tracking_url} — an unrecognised placeholder in a
    # hand-edited template renders as empty rather than raising, so a
    # typo degrades quietly (notifications.whatsapp.message_builder
    # ._SafeTemplateDict). Only six of the eleven Order.Status values
    # have a template — §26 names exactly these six; the rest (Pending
    # Confirmation, Ready to Dispatch, Failed Delivery, Returned, Expired)
    # have none by design.
    whatsapp_template_confirmed = models.TextField(
        default=(
            "Hi {customer_name}, your order {order_number} has been confirmed! "
            "We'll let you know as it progresses."
        )
    )
    whatsapp_template_processing = models.TextField(
        default="Hi {customer_name}, your order {order_number} is now being processed."
    )
    whatsapp_template_dispatched = models.TextField(
        default=(
            "Hi {customer_name}, your order {order_number} has been dispatched with "
            "{courier_name}. Tracking: {tracking_number}"
        )
    )
    whatsapp_template_out_for_delivery = models.TextField(
        default="Hi {customer_name}, your order {order_number} is out for delivery today!"
    )
    whatsapp_template_delivered = models.TextField(
        default=(
            "Hi {customer_name}, your order {order_number} has been delivered. "
            "Thank you for shopping with us!"
        )
    )
    whatsapp_template_cancelled = models.TextField(
        default=(
            "Hi {customer_name}, your order {order_number} has been cancelled. "
            "Please contact us if you have any questions."
        )
    )

    class Meta:
        verbose_name = "Store Settings"
        verbose_name_plural = "Store Settings"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="store_settings_singleton_pk"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(STORE_SETTINGS_CACHE_KEY)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        result = super().delete(*args, **kwargs)
        cache.delete(STORE_SETTINGS_CACHE_KEY)
        return result

    @classmethod
    def load(cls) -> StoreSettings:
        """Return the singleton row, creating it with defaults on first call.

        Cached indefinitely (no TTL) because every request reads this via
        the context processor; ``save()``/``delete()`` invalidate the cache
        explicitly, so an edit is visible on the very next render rather
        than after a TTL expires.
        """
        settings_obj: StoreSettings | None = cache.get(STORE_SETTINGS_CACHE_KEY)
        if settings_obj is None:
            settings_obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(STORE_SETTINGS_CACHE_KEY, settings_obj, timeout=None)
        return settings_obj
