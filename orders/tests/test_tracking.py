"""orders.tracking — the rate limiter and the lookup function (roadmap
Stage 11, requirements §25). HTTP-level tests (byte-identical responses,
the no-PII-leak gate, GET pre-fill) live in test_tracking_views.py.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from orders import tracking
from orders.factories import OrderFactory
from orders.models import OrderTrackingAttempt
from orders.tracking_config import (
    TRACKING_LOCKOUT_FAILURE_THRESHOLD,
    TRACKING_LOCKOUT_WINDOW_SECONDS,
    TRACKING_RATE_LIMIT_MAX_ATTEMPTS,
    TRACKING_RATE_LIMIT_WINDOW_SECONDS,
)


@pytest.mark.django_db
def test_lookup_order_matches_on_order_number_and_phone() -> None:
    order = OrderFactory(customer_phone="+923001234567")

    found = tracking.lookup_order(order_number=order.order_number, raw_mobile_number="03001234567")

    assert found is not None
    assert found.pk == order.pk


@pytest.mark.django_db
def test_lookup_order_is_case_insensitive_on_the_order_number() -> None:
    order = OrderFactory(order_number="ORD-10009-ABC", customer_phone="+923001234567")

    found = tracking.lookup_order(order_number="ord-10009-abc", raw_mobile_number="03001234567")

    assert found is not None
    assert found.pk == order.pk


@pytest.mark.django_db
def test_lookup_order_returns_none_for_an_unknown_order_number() -> None:
    OrderFactory(customer_phone="+923001234567")

    assert (
        tracking.lookup_order(order_number="ORD-99999-XXX", raw_mobile_number="03001234567") is None
    )


@pytest.mark.django_db
def test_lookup_order_returns_none_for_a_mismatched_phone() -> None:
    order = OrderFactory(customer_phone="+923001234567")

    assert (
        tracking.lookup_order(order_number=order.order_number, raw_mobile_number="03009999999")
        is None
    )


@pytest.mark.django_db
def test_lookup_order_returns_none_for_an_unparseable_phone() -> None:
    """A phone that doesn't even normalise (§25's "phone does not match"
    and "not a real phone number" cases must not be distinguishable)."""
    order = OrderFactory(customer_phone="+923001234567")

    assert (
        tracking.lookup_order(order_number=order.order_number, raw_mobile_number="not-a-phone")
        is None
    )


@pytest.mark.django_db
def test_check_rate_limit_allows_attempts_under_the_threshold() -> None:
    for _ in range(TRACKING_RATE_LIMIT_MAX_ATTEMPTS - 1):
        OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.1", order_number="ORD-1-AAA", succeeded=False
        )

    tracking.check_rate_limit(ip_address="10.0.0.1")  # must not raise


@pytest.mark.django_db
def test_gate2_check_rate_limit_triggers_at_the_configured_threshold() -> None:
    for _ in range(TRACKING_RATE_LIMIT_MAX_ATTEMPTS):
        OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.2", order_number="ORD-1-AAA", succeeded=False
        )

    with pytest.raises(tracking.RateLimitedError):
        tracking.check_rate_limit(ip_address="10.0.0.2")


@pytest.mark.django_db
def test_rate_limit_window_only_counts_recent_attempts() -> None:
    stale = timezone.now() - timedelta(seconds=TRACKING_RATE_LIMIT_WINDOW_SECONDS + 5)
    for _ in range(TRACKING_RATE_LIMIT_MAX_ATTEMPTS):
        attempt = OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.3", order_number="ORD-1-AAA", succeeded=False
        )
        attempt.created_at = stale
        attempt.save(update_fields=["created_at"])

    tracking.check_rate_limit(ip_address="10.0.0.3")  # must not raise — all attempts are stale


@pytest.mark.django_db
def test_rate_limit_is_scoped_per_ip() -> None:
    for _ in range(TRACKING_RATE_LIMIT_MAX_ATTEMPTS):
        OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.4", order_number="ORD-1-AAA", succeeded=False
        )

    tracking.check_rate_limit(ip_address="10.0.0.5")  # a different IP — must not raise


@pytest.mark.django_db
def test_gate2_lockout_applies_after_repeated_failures() -> None:
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.6", order_number="ORD-1-AAA", succeeded=False
        )

    with pytest.raises(tracking.LockedOutError):
        tracking.check_rate_limit(ip_address="10.0.0.6")


@pytest.mark.django_db
def test_lockout_is_not_triggered_by_successful_attempts() -> None:
    # Backdated past the short rate-limit window (but still within the
    # longer lockout window) so this test isolates the lockout tier
    # specifically — otherwise the short-window throttle (which counts
    # every attempt, not just failures) would trip first.
    stale_for_rate_limit = timezone.now() - timedelta(
        seconds=TRACKING_RATE_LIMIT_WINDOW_SECONDS + 5
    )
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        attempt = OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.7", order_number="ORD-1-AAA", succeeded=True
        )
        attempt.created_at = stale_for_rate_limit
        attempt.save(update_fields=["created_at"])

    tracking.check_rate_limit(ip_address="10.0.0.7")  # must not raise — none of these failed


@pytest.mark.django_db
def test_lockout_self_expires_as_old_failures_age_out_of_the_window() -> None:
    stale = timezone.now() - timedelta(seconds=TRACKING_LOCKOUT_WINDOW_SECONDS + 5)
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        attempt = OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.8", order_number="ORD-1-AAA", succeeded=False
        )
        attempt.created_at = stale
        attempt.save(update_fields=["created_at"])

    tracking.check_rate_limit(ip_address="10.0.0.8")  # must not raise — all failures are stale


@pytest.mark.django_db
def test_lockout_is_checked_before_the_shorter_rate_limit_window() -> None:
    """A locked-out IP whose failures also happen to exceed the shorter
    rate-limit count must raise LockedOutError specifically, not
    RateLimitedError — the caller (the view) shows a different message
    for each, and the more severe case should win."""
    for _ in range(TRACKING_LOCKOUT_FAILURE_THRESHOLD):
        OrderTrackingAttempt.objects.create(
            ip_address="10.0.0.9", order_number="ORD-1-AAA", succeeded=False
        )

    with pytest.raises(tracking.LockedOutError):
        tracking.check_rate_limit(ip_address="10.0.0.9")


@pytest.mark.django_db
def test_record_attempt_writes_a_row_without_storing_a_phone_number() -> None:
    tracking.record_attempt(ip_address="10.0.0.10", order_number="ord-10002-cpx", succeeded=False)

    row = OrderTrackingAttempt.objects.get()
    assert row.ip_address == "10.0.0.10"
    assert row.order_number == "ORD-10002-CPX"
    assert row.succeeded is False
    assert not hasattr(row, "phone")


@pytest.mark.django_db
def test_record_attempt_logs_a_warning_only_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="orders.tracking")

    tracking.record_attempt(ip_address="10.0.0.11", order_number="ORD-1-AAA", succeeded=True)
    assert not caplog.records

    tracking.record_attempt(ip_address="10.0.0.11", order_number="ORD-1-AAA", succeeded=False)
    assert len(caplog.records) == 1
    assert "10.0.0.11" in caplog.records[0].message
