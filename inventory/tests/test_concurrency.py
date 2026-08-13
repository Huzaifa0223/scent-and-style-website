"""The highest-consequence tests in this project (roadmap Stage 4 gate 5):
two simultaneous reservations for the last unit, exactly one succeeds, the
other fails cleanly. Real threads, real separate database connections, a
real commit — not a mock, and not manage.py shell's autocommit either
(specs/state.md already records why shell's autocommit doesn't reproduce
pytest's default rolled-back-transaction isolation; the same distinction
matters here in reverse). ``transaction=True`` is required, not a style
choice: the default ``django_db`` marker never commits the fixture data,
so a second thread's own connection couldn't see it at all under
Postgres's read-committed isolation.

The barrier-synchronised race test alone was verified, not assumed, to
have teeth: run once against a build of ``reserve()`` with
``select_for_update()`` removed, it produced 104 oversells out of 200
iterations (52%); restored, 0 out of 200. That verification isn't
reproduced here as a committed test (it requires editing services.py to
prove a negative), but ``test_reserve_locks_the_variant_row_with_select_for_update``
below is the permanent, deterministic version of the same guarantee — it
asserts the lock is actually issued, rather than relying on timing to
occasionally expose its absence.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.db.models import Sum
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.factories import ProductVariantFactory
from inventory import services
from inventory.factories import StockReservationFactory
from inventory.models import StockReservation
from orders.factories import OrderFactory


@pytest.mark.django_db
def test_reserve_locks_the_variant_row_with_select_for_update() -> None:
    """Deterministic regression guard: asserts the mechanism is present,
    not just that the outcome happened to be correct on this run — a
    timing-based race test can pass even when the lock has been removed
    (see this module's docstring)."""
    variant = ProductVariantFactory(stock_quantity=5)

    with CaptureQueriesContext(connection) as captured:
        services.reserve(variant_id=variant.pk, quantity=1, order=OrderFactory())

    assert any("FOR UPDATE" in query["sql"] for query in captured.captured_queries)


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_reservations_for_the_last_unit_exactly_one_succeeds() -> None:
    variant = ProductVariantFactory(stock_quantity=1)
    # Two different orders, standing in for two different customers racing
    # for the same last unit — created upfront (main thread, committed
    # before the workers start, same as `variant`) rather than inside
    # attempt() itself, so the race is only ever over reserve(), not also
    # over factory-boy's sequence counters across threads.
    orders = {"t0": OrderFactory(), "t1": OrderFactory()}
    outcomes: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def attempt(label: str) -> None:
        try:
            barrier.wait(timeout=5)
            services.reserve(variant_id=variant.pk, quantity=1, order=orders[label])
            outcomes[label] = "reserved"
        except services.InsufficientStockError:
            outcomes[label] = "rejected"
        finally:
            connection.close()  # Django doesn't auto-close a thread's own connection

    threads = [threading.Thread(target=attempt, args=(f"t{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes.values()) == ["rejected", "reserved"]
    # Ground truth from the database, not just what each thread reported —
    # catches a scenario where both threads actually succeeded despite a
    # race in the outcomes dict itself.
    assert StockReservation.objects.filter(variant=variant).count() == 1
    variant.refresh_from_db()
    assert variant.stock_quantity == 1  # reserve() never touches on-hand stock


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_reservations_with_enough_stock_for_both_both_succeed() -> None:
    """The non-adversarial sibling: concurrency must not reject requests
    that both fit, only ones that don't."""
    variant = ProductVariantFactory(stock_quantity=5)
    orders = {"t0": OrderFactory(), "t1": OrderFactory()}
    outcomes: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def attempt(label: str) -> None:
        try:
            barrier.wait(timeout=5)
            services.reserve(variant_id=variant.pk, quantity=2, order=orders[label])
            outcomes[label] = "reserved"
        except services.InsufficientStockError:
            outcomes[label] = "rejected"
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(f"t{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert list(outcomes.values()) == ["reserved", "reserved"]
    total = StockReservation.objects.filter(variant=variant).aggregate(total=Sum("quantity"))[
        "total"
    ]
    assert total == 4


@pytest.mark.django_db(transaction=True)
def test_gate6_sweeper_is_safe_to_run_twice_concurrently() -> None:
    variant = ProductVariantFactory(stock_quantity=10)
    for _ in range(5):
        StockReservationFactory(variant=variant, expires_at=timezone.now() - timedelta(hours=1))

    released_counts: list[int] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(2)

    def sweep() -> None:
        try:
            barrier.wait(timeout=5)
            count = services.release_expired_reservations()
            with results_lock:
                released_counts.append(count)
        finally:
            connection.close()

    threads = [threading.Thread(target=sweep) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sum(released_counts) == 5  # no double-counting, none missed
    assert StockReservation.objects.filter(variant=variant).count() == 0
