"""factory-boy fixtures for the customers app."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from .models import Customer


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer

    name = factory.Sequence(lambda n: f"Customer {n}")
    phone = factory.Sequence(lambda n: f"+9230000{n:05d}")
