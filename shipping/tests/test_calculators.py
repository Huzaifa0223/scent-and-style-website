"""shipping.calculators — the three DeliveryCalculator strategies and the
get_delivery_calculator() factory (roadmap Stage 8 gate 6).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shipping.calculators import (
    CityBasedCalculator,
    FlatRateCalculator,
    FreeAboveThresholdCalculator,
    get_delivery_calculator,
)
from shipping.factories import DeliveryZoneFactory
from store.models import DeliveryStrategy, StoreSettings


def test_flat_rate_calculator_ignores_subtotal_and_city() -> None:
    calculator = FlatRateCalculator(rate=Decimal("150.00"))

    assert calculator.calculate(subtotal=Decimal("0.00"), city="Karachi") == Decimal("150.00")
    assert calculator.calculate(subtotal=Decimal("100000.00"), city="Lahore") == Decimal("150.00")


def test_free_above_threshold_calculator_charges_below_threshold() -> None:
    calculator = FreeAboveThresholdCalculator(rate=Decimal("150.00"), threshold=Decimal("5000.00"))

    assert calculator.calculate(subtotal=Decimal("4999.99"), city="Karachi") == Decimal("150.00")


def test_free_above_threshold_calculator_waives_at_and_above_threshold() -> None:
    calculator = FreeAboveThresholdCalculator(rate=Decimal("150.00"), threshold=Decimal("5000.00"))

    assert calculator.calculate(subtotal=Decimal("5000.00"), city="Karachi") == Decimal("0.00")
    assert calculator.calculate(subtotal=Decimal("9999.00"), city="Karachi") == Decimal("0.00")


@pytest.mark.django_db
def test_city_based_calculator_uses_the_zone_rate_for_a_known_city() -> None:
    DeliveryZoneFactory(city="Lahore", charge=Decimal("250.00"))
    calculator = CityBasedCalculator(fallback_rate=Decimal("300.00"), threshold=None)

    assert calculator.calculate(subtotal=Decimal("100.00"), city="Lahore") == Decimal("250.00")


@pytest.mark.django_db
def test_city_based_calculator_matches_case_insensitively() -> None:
    DeliveryZoneFactory(city="Lahore", charge=Decimal("250.00"))
    calculator = CityBasedCalculator(fallback_rate=Decimal("300.00"), threshold=None)

    assert calculator.calculate(subtotal=Decimal("100.00"), city="LAHORE") == Decimal("250.00")
    assert calculator.calculate(subtotal=Decimal("100.00"), city="lahore") == Decimal("250.00")


@pytest.mark.django_db
def test_city_based_calculator_falls_back_for_an_unlisted_city() -> None:
    DeliveryZoneFactory(city="Lahore", charge=Decimal("250.00"))
    calculator = CityBasedCalculator(fallback_rate=Decimal("300.00"), threshold=None)

    assert calculator.calculate(subtotal=Decimal("100.00"), city="Multan") == Decimal("300.00")


@pytest.mark.django_db
def test_city_based_calculator_waives_the_zone_rate_above_its_own_threshold() -> None:
    """Gate 6 — the free-delivery threshold combined with city rates."""
    DeliveryZoneFactory(city="Lahore", charge=Decimal("250.00"))
    calculator = CityBasedCalculator(fallback_rate=Decimal("300.00"), threshold=Decimal("5000.00"))

    assert calculator.calculate(subtotal=Decimal("5000.00"), city="Lahore") == Decimal("0.00")
    assert calculator.calculate(subtotal=Decimal("4999.99"), city="Lahore") == Decimal("250.00")


@pytest.mark.django_db
def test_get_delivery_calculator_builds_flat_rate_by_default() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FLAT_RATE
    settings_obj.flat_delivery_rate = Decimal("175.00")
    settings_obj.save()

    calculator = get_delivery_calculator()

    assert isinstance(calculator, FlatRateCalculator)
    assert calculator.rate == Decimal("175.00")


@pytest.mark.django_db
def test_get_delivery_calculator_builds_free_above_threshold() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FREE_ABOVE_THRESHOLD
    settings_obj.flat_delivery_rate = Decimal("175.00")
    settings_obj.free_delivery_threshold = Decimal("3000.00")
    settings_obj.save()

    calculator = get_delivery_calculator()

    assert isinstance(calculator, FreeAboveThresholdCalculator)
    assert calculator.rate == Decimal("175.00")
    assert calculator.threshold == Decimal("3000.00")


@pytest.mark.django_db
def test_get_delivery_calculator_falls_back_to_flat_rate_when_threshold_is_unset() -> None:
    """A merchant selecting FREE_ABOVE_THRESHOLD without configuring a
    threshold has misconfigured it, not selected "never free" — treating
    the unset threshold as infinite (always charge) is the safer of two
    wrong defaults."""
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.FREE_ABOVE_THRESHOLD
    settings_obj.flat_delivery_rate = Decimal("175.00")
    settings_obj.free_delivery_threshold = None
    settings_obj.save()

    calculator = get_delivery_calculator()

    assert isinstance(calculator, FlatRateCalculator)
    assert calculator.rate == Decimal("175.00")


@pytest.mark.django_db
def test_get_delivery_calculator_builds_city_based() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.delivery_strategy = DeliveryStrategy.CITY_BASED
    settings_obj.city_fallback_delivery_rate = Decimal("300.00")
    settings_obj.free_delivery_threshold = Decimal("5000.00")
    settings_obj.save()

    calculator = get_delivery_calculator()

    assert isinstance(calculator, CityBasedCalculator)
    assert calculator.fallback_rate == Decimal("300.00")
    assert calculator.threshold == Decimal("5000.00")
