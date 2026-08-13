"""The three ``DeliveryCalculator`` strategies (§27) and the factory that
selects one from ``StoreSettings``. Checkout (and any other caller) must
go through ``get_delivery_calculator()``, never a concrete class directly
— same discipline as ``search.backends.get_search_backend()`` — so a
storefront view importing e.g. ``FlatRateCalculator`` by name is checked
for the same way Stage 5 checks for a direct ``PostgresSearchBackend``
import.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from store.models import DeliveryStrategy, StoreSettings

from .models import DeliveryZone
from .protocols import DeliveryCalculator


@dataclass(frozen=True)
class FlatRateCalculator:
    rate: Decimal

    def calculate(self, *, subtotal: Decimal, city: str) -> Decimal:
        return self.rate


@dataclass(frozen=True)
class FreeAboveThresholdCalculator:
    rate: Decimal
    threshold: Decimal

    def calculate(self, *, subtotal: Decimal, city: str) -> Decimal:
        return Decimal("0.00") if subtotal >= self.threshold else self.rate


@dataclass(frozen=True)
class CityBasedCalculator:
    """``threshold`` is optional — city-based rates "can carry" a
    free-delivery threshold (§27), they don't require one."""

    fallback_rate: Decimal
    threshold: Decimal | None

    def calculate(self, *, subtotal: Decimal, city: str) -> Decimal:
        if self.threshold is not None and subtotal >= self.threshold:
            return Decimal("0.00")
        zone = DeliveryZone.objects.filter(city__iexact=city).first()
        return zone.charge if zone is not None else self.fallback_rate


def get_delivery_calculator() -> DeliveryCalculator:
    settings_obj = StoreSettings.load()
    if settings_obj.delivery_strategy == DeliveryStrategy.FREE_ABOVE_THRESHOLD:
        # A merchant selecting this strategy without setting a threshold
        # has misconfigured it, not selected "no threshold" — treating a
        # None threshold as infinite (never free) is the safer of two
        # wrong defaults, and mirrors the strategy's own name.
        threshold = settings_obj.free_delivery_threshold
        if threshold is None:
            return FlatRateCalculator(rate=settings_obj.flat_delivery_rate)
        return FreeAboveThresholdCalculator(
            rate=settings_obj.flat_delivery_rate, threshold=threshold
        )
    if settings_obj.delivery_strategy == DeliveryStrategy.CITY_BASED:
        return CityBasedCalculator(
            fallback_rate=settings_obj.city_fallback_delivery_rate,
            threshold=settings_obj.free_delivery_threshold,
        )
    return FlatRateCalculator(rate=settings_obj.flat_delivery_rate)
