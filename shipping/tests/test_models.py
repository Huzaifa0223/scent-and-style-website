from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from shipping.factories import DeliveryZoneFactory


@pytest.mark.django_db
def test_city_uniqueness_is_case_insensitive() -> None:
    DeliveryZoneFactory(city="Lahore", charge=Decimal("200.00"))
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeliveryZoneFactory(city="lahore", charge=Decimal("250.00"))
