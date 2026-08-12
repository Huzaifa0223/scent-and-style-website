"""factory-boy fixtures for the inventory app."""

from __future__ import annotations

from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from catalog.factories import ProductVariantFactory

from .models import InventoryAdjustment, StockReservation


class StockReservationFactory(DjangoModelFactory):
    class Meta:
        model = StockReservation

    variant = factory.SubFactory(ProductVariantFactory)
    quantity = 1
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=24))


class InventoryAdjustmentFactory(DjangoModelFactory):
    class Meta:
        model = InventoryAdjustment

    variant = factory.SubFactory(ProductVariantFactory)
    delta = 1
    reason = InventoryAdjustment.Reason.MANUAL
