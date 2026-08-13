"""``DeliveryCalculator`` protocol (requirements §27)."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class DeliveryCalculator(Protocol):
    def calculate(self, *, subtotal: Decimal, city: str) -> Decimal: ...
