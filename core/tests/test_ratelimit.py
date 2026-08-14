"""core/ratelimit.py (§41, roadmap Stage 13) — the shared sliding-window
limiter behind login, checkout, and search. Scope isolation (a login
attempt from an IP must not count against that same IP's checkout
budget) is the one behaviour unique to sharing a table across scopes, on
top of everything orders/tests/test_tracking.py already proved for the
single-scope case this generalises.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory, override_settings

from core.models import RateLimitScope
from core.ratelimit import (
    LockedOutError,
    RateLimitedError,
    RateLimitPolicy,
    check_rate_limit,
    client_ip,
    record_attempt,
)

pytestmark = pytest.mark.django_db

_POLICY_WITH_LOCKOUT = RateLimitPolicy(
    max_attempts=3, window_seconds=60, lockout_failure_threshold=2, lockout_window_seconds=3600
)
_POLICY_WITHOUT_LOCKOUT = RateLimitPolicy(max_attempts=3, window_seconds=60)


def test_check_rate_limit_allows_requests_under_the_threshold() -> None:
    for _ in range(2):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", succeeded=True)

    check_rate_limit(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", policy=_POLICY_WITH_LOCKOUT)


def test_check_rate_limit_raises_rate_limited_at_the_threshold() -> None:
    for _ in range(3):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", succeeded=True)

    with pytest.raises(RateLimitedError):
        check_rate_limit(
            scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", policy=_POLICY_WITH_LOCKOUT
        )


def test_check_rate_limit_raises_locked_out_before_rate_limited_when_both_trip() -> None:
    for _ in range(2):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", succeeded=False)

    with pytest.raises(LockedOutError):
        check_rate_limit(
            scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", policy=_POLICY_WITH_LOCKOUT
        )


def test_check_rate_limit_never_raises_locked_out_when_policy_has_no_lockout_tier() -> None:
    for _ in range(2):
        record_attempt(scope=RateLimitScope.SEARCH, ip_address="10.0.0.1", succeeded=False)

    check_rate_limit(
        scope=RateLimitScope.SEARCH, ip_address="10.0.0.1", policy=_POLICY_WITHOUT_LOCKOUT
    )


def test_check_rate_limit_still_rate_limits_a_lockout_free_policy_on_raw_volume() -> None:
    for _ in range(3):
        record_attempt(scope=RateLimitScope.SEARCH, ip_address="10.0.0.1", succeeded=True)

    with pytest.raises(RateLimitedError):
        check_rate_limit(
            scope=RateLimitScope.SEARCH, ip_address="10.0.0.1", policy=_POLICY_WITHOUT_LOCKOUT
        )


def test_scopes_are_isolated_from_one_another() -> None:
    for _ in range(3):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", succeeded=True)

    # Same IP, different scope — its own, still-empty budget.
    check_rate_limit(
        scope=RateLimitScope.CHECKOUT, ip_address="10.0.0.1", policy=_POLICY_WITH_LOCKOUT
    )


def test_ip_addresses_are_isolated_from_one_another() -> None:
    for _ in range(3):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="10.0.0.1", succeeded=True)

    check_rate_limit(scope=RateLimitScope.LOGIN, ip_address="10.0.0.2", policy=_POLICY_WITH_LOCKOUT)


def test_client_ip_uses_remote_addr_by_default() -> None:
    request = RequestFactory().get(
        "/", REMOTE_ADDR="203.0.113.5", HTTP_X_FORWARDED_FOR="198.51.100.9"
    )

    assert client_ip(request) == "203.0.113.5"


@override_settings(TRUST_X_FORWARDED_FOR=True)
def test_client_ip_trusts_the_last_x_forwarded_for_hop_when_configured() -> None:
    """Caddy appends the real client address as the last entry — see
    core.ratelimit.client_ip's own docstring for why only the last hop
    of a single, trusted proxy is honoured, not the whole header."""
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="10.0.0.1",  # Caddy's own address, from gunicorn's view
        HTTP_X_FORWARDED_FOR="203.0.113.5, 198.51.100.9",
    )

    assert client_ip(request) == "198.51.100.9"


@override_settings(TRUST_X_FORWARDED_FOR=True)
def test_client_ip_falls_back_to_remote_addr_when_the_header_is_absent() -> None:
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.5")

    assert client_ip(request) == "203.0.113.5"
