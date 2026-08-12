"""The release_expired_reservations management command (§10.4) — a thin
wrapper around inventory.services.release_expired_reservations(); the
concurrency guarantee itself is proven against the service function
directly in test_concurrency.py::test_gate6_..., not re-proven here.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from catalog.factories import ProductVariantFactory
from inventory.factories import StockReservationFactory
from inventory.models import StockReservation


@pytest.mark.django_db
def test_command_releases_expired_reservations_and_reports_the_count() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    expired = StockReservationFactory(
        variant=variant, expires_at=timezone.now() - timedelta(hours=1)
    )
    active = StockReservationFactory(
        variant=variant, expires_at=timezone.now() + timedelta(hours=1)
    )

    out = StringIO()
    call_command("release_expired_reservations", stdout=out)

    assert "Released 1 expired reservation(s)." in out.getvalue()
    assert not StockReservation.objects.filter(pk=expired.pk).exists()
    assert StockReservation.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_command_reports_zero_when_nothing_is_expired() -> None:
    out = StringIO()
    call_command("release_expired_reservations", stdout=out)
    assert "Released 0 expired reservation(s)." in out.getvalue()
