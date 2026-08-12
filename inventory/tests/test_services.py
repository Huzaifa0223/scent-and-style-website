"""inventory.services — the reservation lifecycle (§10.1) and manual
adjustment, outside of the concurrency guarantees (see test_concurrency.py
for those). Acceptance gates 1-4 and 7 live here.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from catalog.factories import ProductFactory, ProductVariantFactory
from catalog.models import ProductVariant
from inventory import services
from inventory.factories import StockReservationFactory
from inventory.models import InventoryAdjustment, StockReservation
from store.models import StoreSettings


@pytest.mark.django_db
def test_reserve_creates_a_reservation_expiring_at_store_settings_ttl() -> None:
    StoreSettings.load()  # seed the singleton with its default ttl (24h)
    variant = ProductVariantFactory(stock_quantity=10)
    before = timezone.now()

    reservation = services.reserve(variant_id=variant.pk, quantity=3)

    assert reservation.variant_id == variant.pk
    assert reservation.quantity == 3
    assert before + timedelta(hours=23, minutes=59) < reservation.expires_at
    assert reservation.expires_at < before + timedelta(hours=24, minutes=1)
    # reserve() never touches on-hand stock — that's the whole point of §10.1.
    variant.refresh_from_db()
    assert variant.stock_quantity == 10


@pytest.mark.django_db
def test_reserve_honours_an_explicit_ttl_override() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    before = timezone.now()

    reservation = services.reserve(variant_id=variant.pk, quantity=1, ttl_hours=2)

    assert before + timedelta(hours=1, minutes=59) < reservation.expires_at
    assert reservation.expires_at < before + timedelta(hours=2, minutes=1)


@pytest.mark.django_db
def test_reserve_raises_insufficient_stock_when_not_enough_available() -> None:
    variant = ProductVariantFactory(stock_quantity=2)

    with pytest.raises(services.InsufficientStockError):
        services.reserve(variant_id=variant.pk, quantity=3)

    assert StockReservation.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_reserve_subtracts_existing_active_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    StockReservationFactory(variant=variant, quantity=4)

    with pytest.raises(services.InsufficientStockError):
        services.reserve(variant_id=variant.pk, quantity=2)  # only 1 left

    reservation = services.reserve(variant_id=variant.pk, quantity=1)
    assert reservation.quantity == 1


@pytest.mark.django_db
def test_reserve_ignores_expired_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    StockReservationFactory(
        variant=variant, quantity=5, expires_at=timezone.now() - timedelta(hours=1)
    )

    reservation = services.reserve(variant_id=variant.pk, quantity=5)
    assert reservation.quantity == 5


@pytest.mark.django_db
def test_reserve_rejects_zero_or_negative_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    with pytest.raises(ValidationError):
        services.reserve(variant_id=variant.pk, quantity=0)
    with pytest.raises(ValidationError):
        services.reserve(variant_id=variant.pk, quantity=-1)


@pytest.mark.django_db
def test_available_quantity_annotation_reflects_active_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    StockReservationFactory(variant=variant, quantity=4)
    StockReservationFactory(
        variant=variant, quantity=100, expires_at=timezone.now() - timedelta(hours=1)
    )

    annotated = ProductVariant.objects.with_available_quantity().get(pk=variant.pk)
    assert annotated.available_quantity == 6  # 10 - 4 active; the expired 100 doesn't count


@pytest.mark.django_db
def test_commit_reservation_rejects_a_reservation_that_would_take_stock_negative() -> None:
    """Guards against stock_quantity having been reduced below the
    reservation's own quantity by some other path (a manual adjustment)
    between the reservation being created and confirmed."""
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=8)
    services.adjust(variant_id=variant.pk, absolute_quantity=2)  # drops below the reservation

    with pytest.raises(ValidationError):
        services.commit_reservation(reservation_id=reservation.pk)

    assert StockReservation.objects.filter(pk=reservation.pk).exists()
    variant.refresh_from_db()
    assert variant.stock_quantity == 2


@pytest.mark.django_db
def test_restore_rejects_zero_or_negative_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    with pytest.raises(ValidationError):
        services.restore(
            variant_id=variant.pk, quantity=0, reason=InventoryAdjustment.Reason.ORDER_RETURNED
        )
    with pytest.raises(ValidationError):
        services.restore(
            variant_id=variant.pk, quantity=-1, reason=InventoryAdjustment.Reason.ORDER_RETURNED
        )


@pytest.mark.django_db
def test_gate1_reserve_then_confirm_decrements_stock_and_clears_reservation() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3)

    services.commit_reservation(reservation_id=reservation.pk)

    variant.refresh_from_db()
    assert variant.stock_quantity == 7
    assert not StockReservation.objects.filter(pk=reservation.pk).exists()
    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.delta == -3
    assert adjustment.reason == InventoryAdjustment.Reason.ORDER_CONFIRMED


@pytest.mark.django_db
def test_gate2_reserve_then_expire_releases_and_leaves_stock_untouched() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = StockReservationFactory(
        variant=variant, quantity=3, expires_at=timezone.now() - timedelta(minutes=1)
    )

    released_count = services.release_expired_reservations()

    assert released_count == 1
    assert not StockReservation.objects.filter(pk=reservation.pk).exists()
    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    assert InventoryAdjustment.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_gate3_reserve_then_cancel_releases_without_touching_stock() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3)

    services.release(reservation_id=reservation.pk)

    assert not StockReservation.objects.filter(pk=reservation.pk).exists()
    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    assert InventoryAdjustment.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_release_of_an_already_released_reservation_is_a_silent_no_op() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3)
    services.release(reservation_id=reservation.pk)

    services.release(reservation_id=reservation.pk)  # must not raise


@pytest.mark.django_db
def test_gate4_restore_after_post_confirmation_cancellation_increments_stock() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3)
    services.commit_reservation(reservation_id=reservation.pk)
    variant.refresh_from_db()
    assert variant.stock_quantity == 7

    services.restore(
        variant_id=variant.pk,
        quantity=3,
        reason=InventoryAdjustment.Reason.ORDER_CANCELLED,
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    adjustment = InventoryAdjustment.objects.get(
        variant=variant, reason=InventoryAdjustment.Reason.ORDER_CANCELLED
    )
    assert adjustment.delta == 3


@pytest.mark.django_db
def test_gate7_manual_adjustment_writes_an_inventory_adjustment_row() -> None:
    variant = ProductVariantFactory(stock_quantity=10)

    updated = services.adjust(variant_id=variant.pk, absolute_quantity=47, note="Recount")

    assert updated.stock_quantity == 47
    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.delta == 37
    assert adjustment.reason == InventoryAdjustment.Reason.MANUAL
    assert adjustment.note == "Recount"


@pytest.mark.django_db
def test_adjust_to_the_same_quantity_is_a_no_op_and_writes_no_adjustment() -> None:
    variant = ProductVariantFactory(stock_quantity=10)

    services.adjust(variant_id=variant.pk, absolute_quantity=10)

    assert InventoryAdjustment.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_adjust_rejects_a_negative_absolute_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    with pytest.raises(ValidationError):
        services.adjust(variant_id=variant.pk, absolute_quantity=-1)


@pytest.mark.django_db
def test_commit_reservation_records_the_actor() -> None:
    user_model = get_user_model()
    owner = user_model.objects.create_user(username="owner", password="x")
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=1)

    services.commit_reservation(reservation_id=reservation.pk, actor=owner)

    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.actor == owner


@pytest.mark.django_db
def test_deleting_the_actor_leaves_the_adjustment_row_with_a_null_actor() -> None:
    """Append-only audit trail — the row must outlive the user account."""
    user_model = get_user_model()
    staffer = user_model.objects.create_user(username="staffer", password="x")
    variant = ProductVariantFactory(stock_quantity=10)
    services.adjust(variant_id=variant.pk, absolute_quantity=5, actor=staffer)

    staffer.delete()

    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.actor_id is None
    assert adjustment.delta == -5


@pytest.mark.django_db
def test_release_expired_reservations_returns_zero_when_nothing_is_expired() -> None:
    ProductFactory(default_variant_price=Decimal("10.00"))
    assert services.release_expired_reservations() == 0
