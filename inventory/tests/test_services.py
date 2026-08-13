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
from orders.factories import OrderFactory, OrderItemFactory
from store.models import StoreSettings


@pytest.mark.django_db
def test_reserve_creates_a_reservation_expiring_at_store_settings_ttl() -> None:
    StoreSettings.load()  # seed the singleton with its default ttl (24h)
    variant = ProductVariantFactory(stock_quantity=10)
    before = timezone.now()

    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())

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

    reservation = services.reserve(
        variant_id=variant.pk, quantity=1, ttl_hours=2, order=OrderFactory()
    )

    assert before + timedelta(hours=1, minutes=59) < reservation.expires_at
    assert reservation.expires_at < before + timedelta(hours=2, minutes=1)


@pytest.mark.django_db
def test_reserve_raises_insufficient_stock_when_not_enough_available() -> None:
    variant = ProductVariantFactory(stock_quantity=2)

    with pytest.raises(services.InsufficientStockError):
        services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())

    assert StockReservation.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_reserve_subtracts_existing_active_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    StockReservationFactory(variant=variant, quantity=4)

    with pytest.raises(services.InsufficientStockError):
        services.reserve(variant_id=variant.pk, quantity=2, order=OrderFactory())  # only 1 left

    reservation = services.reserve(variant_id=variant.pk, quantity=1, order=OrderFactory())
    assert reservation.quantity == 1


@pytest.mark.django_db
def test_reserve_ignores_expired_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    StockReservationFactory(
        variant=variant, quantity=5, expires_at=timezone.now() - timedelta(hours=1)
    )

    reservation = services.reserve(variant_id=variant.pk, quantity=5, order=OrderFactory())
    assert reservation.quantity == 5


@pytest.mark.django_db
def test_reserve_rejects_zero_or_negative_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=5)
    with pytest.raises(ValidationError):
        services.reserve(variant_id=variant.pk, quantity=0, order=OrderFactory())
    with pytest.raises(ValidationError):
        services.reserve(variant_id=variant.pk, quantity=-1, order=OrderFactory())


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
    reservation = services.reserve(variant_id=variant.pk, quantity=8, order=OrderFactory())
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
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())

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
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())

    services.release(reservation_id=reservation.pk)

    assert not StockReservation.objects.filter(pk=reservation.pk).exists()
    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    assert InventoryAdjustment.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_release_of_an_already_released_reservation_is_a_silent_no_op() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())
    services.release(reservation_id=reservation.pk)

    services.release(reservation_id=reservation.pk)  # must not raise


@pytest.mark.django_db
def test_gate4_restore_after_post_confirmation_cancellation_increments_stock() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=OrderFactory())
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
    reservation = services.reserve(variant_id=variant.pk, quantity=1, order=OrderFactory())

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


# --- roadmap Stage 10 additions: release_reserved, consume, and the
# --- per-order bulk wrappers orders/ calls instead of touching
# --- StockReservation itself. -----------------------------------------


@pytest.mark.django_db
def test_release_reserved_shrinks_a_single_reservation_row() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    reservation = services.reserve(variant_id=variant.pk, quantity=5, order=order)

    services.release_reserved(variant_id=variant.pk, order=order, quantity=2)

    reservation.refresh_from_db()
    assert reservation.quantity == 3
    variant.refresh_from_db()
    assert variant.stock_quantity == 10  # never touched


@pytest.mark.django_db
def test_release_reserved_deletes_the_row_when_fully_consumed() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=order)

    services.release_reserved(variant_id=variant.pk, order=order, quantity=3)

    assert not StockReservation.objects.filter(pk=reservation.pk).exists()


@pytest.mark.django_db
def test_release_reserved_spans_multiple_reservation_rows_oldest_first() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    first = services.reserve(variant_id=variant.pk, quantity=2, order=order)
    second = services.reserve(variant_id=variant.pk, quantity=4, order=order)

    services.release_reserved(variant_id=variant.pk, order=order, quantity=3)

    assert not StockReservation.objects.filter(pk=first.pk).exists()
    second.refresh_from_db()
    assert second.quantity == 3  # 4 - (3 - 2) consumed from the first row


@pytest.mark.django_db
def test_release_reserved_ignores_another_orders_reservations_for_the_same_variant() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    other_order = OrderFactory()
    services.reserve(variant_id=variant.pk, quantity=3, order=other_order)
    reservation = services.reserve(variant_id=variant.pk, quantity=3, order=order)

    services.release_reserved(variant_id=variant.pk, order=order, quantity=3)

    assert not StockReservation.objects.filter(pk=reservation.pk).exists()
    assert StockReservation.objects.filter(order=other_order, quantity=3).exists()


@pytest.mark.django_db
def test_release_reserved_raises_when_the_order_holds_less_than_requested() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    services.reserve(variant_id=variant.pk, quantity=2, order=order)

    with pytest.raises(ValidationError):
        services.release_reserved(variant_id=variant.pk, order=order, quantity=5)


@pytest.mark.django_db
def test_release_reserved_rejects_zero_or_negative_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    order = OrderFactory()
    with pytest.raises(ValidationError):
        services.release_reserved(variant_id=variant.pk, order=order, quantity=0)


@pytest.mark.django_db
def test_consume_decrements_stock_directly_and_writes_an_adjustment() -> None:
    variant = ProductVariantFactory(stock_quantity=10)

    services.consume(
        variant_id=variant.pk, quantity=4, reason=InventoryAdjustment.Reason.ORDER_EDITED
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 6
    adjustment = InventoryAdjustment.objects.get(variant=variant)
    assert adjustment.delta == -4
    assert adjustment.reason == InventoryAdjustment.Reason.ORDER_EDITED
    assert StockReservation.objects.filter(variant=variant).count() == 0


@pytest.mark.django_db
def test_consume_respects_other_orders_active_reservations() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    StockReservationFactory(variant=variant, quantity=7)

    with pytest.raises(services.InsufficientStockError):
        services.consume(
            variant_id=variant.pk, quantity=4, reason=InventoryAdjustment.Reason.ORDER_EDITED
        )

    variant.refresh_from_db()
    assert variant.stock_quantity == 10  # rejected attempt touched nothing


@pytest.mark.django_db
def test_consume_rejects_zero_or_negative_quantity() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    with pytest.raises(ValidationError):
        services.consume(
            variant_id=variant.pk, quantity=0, reason=InventoryAdjustment.Reason.ORDER_EDITED
        )


@pytest.mark.django_db
def test_commit_all_for_order_commits_every_reservation_the_order_holds() -> None:
    order = OrderFactory()
    variant_a = ProductVariantFactory(stock_quantity=10)
    variant_b = ProductVariantFactory(stock_quantity=10)
    services.reserve(variant_id=variant_a.pk, quantity=3, order=order)
    services.reserve(variant_id=variant_b.pk, quantity=2, order=order)

    services.commit_all_for_order(order=order)

    variant_a.refresh_from_db()
    variant_b.refresh_from_db()
    assert variant_a.stock_quantity == 7
    assert variant_b.stock_quantity == 8
    assert StockReservation.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_release_all_for_order_releases_every_reservation_without_touching_stock() -> None:
    order = OrderFactory()
    variant = ProductVariantFactory(stock_quantity=10)
    services.reserve(variant_id=variant.pk, quantity=3, order=order)

    services.release_all_for_order(order=order)

    variant.refresh_from_db()
    assert variant.stock_quantity == 10
    assert StockReservation.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_restore_all_for_order_restores_each_lines_current_quantity() -> None:
    order = OrderFactory()
    variant = ProductVariantFactory(stock_quantity=10)
    OrderItemFactory(order=order, variant=variant, quantity=3)
    services.commit_reservation(
        reservation_id=services.reserve(variant_id=variant.pk, quantity=3, order=order).pk
    )
    variant.refresh_from_db()
    assert variant.stock_quantity == 7

    services.restore_all_for_order(order=order, reason=InventoryAdjustment.Reason.ORDER_CANCELLED)

    variant.refresh_from_db()
    assert variant.stock_quantity == 10


@pytest.mark.django_db
def test_restore_all_for_order_skips_a_line_whose_variant_was_deleted() -> None:
    order = OrderFactory()
    product = ProductFactory()
    variant = product.variants.get()
    variant.stock_quantity = 10
    variant.save(update_fields=["stock_quantity", "updated_at"])
    ProductVariantFactory(product=product)  # so the product still has >=1 variant after delete
    OrderItemFactory(order=order, variant=variant, quantity=2)
    variant.delete()  # SET_NULL — item.variant_id is now None

    services.restore_all_for_order(order=order, reason=InventoryAdjustment.Reason.ORDER_RETURNED)

    assert InventoryAdjustment.objects.count() == 0
