"""Delivery domain model (requirements §27, roadmap Stage 8)."""

from __future__ import annotations

from django.db import models
from django.db.models.functions import Upper

from core.models import TimeStampedModel


class DeliveryZone(TimeStampedModel):
    """city -> charge, for the city-based delivery strategy
    (``shipping.calculators.CityBasedCalculator``). Managed via Django
    admin only this stage — no roadmap stage assigns a portal CRUD for it,
    same gap class as the missing Customers portal page (recorded in
    state.md).

    Uniqueness is case-insensitive (``Upper("city")``), not a plain
    ``unique=True`` on the raw string: the calculator matches via
    ``city__iexact``, so a case-sensitive-only constraint would let
    ``"Lahore"`` and ``"lahore"`` both exist as separate, individually
    valid rows — at which point the ``iexact`` lookup becomes
    non-deterministic between them (no natural row order). This
    constraint is what actually prevents that pair from ever being
    created, rather than merely hoping the merchant doesn't type a city
    twice with different casing.
    """

    city = models.CharField(max_length=100)
    charge = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["city"]
        constraints = [
            models.UniqueConstraint(Upper("city"), name="deliveryzone_city_unique_ci"),
        ]

    def __str__(self) -> str:
        return f"{self.city}: {self.charge}"
