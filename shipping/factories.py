"""factory-boy fixtures for the shipping app."""

from __future__ import annotations

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from .models import DeliveryZone


class DeliveryZoneFactory(DjangoModelFactory):
    class Meta:
        model = DeliveryZone

    city = factory.Sequence(lambda n: f"City {n}")
    charge = Decimal("150.00")
