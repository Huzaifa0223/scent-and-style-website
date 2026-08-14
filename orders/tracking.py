"""Public order tracking (§25, roadmap Stage 11). **Rate limiting is the
actual security control here, not the order-number format** — §25's own
words, restated by the roadmap's Stage 11 acceptance gates. Built and
gated before the lookup logic below it, not layered on afterward: the
view calls ``check_rate_limit()`` before it ever calls ``lookup_order()``,
and a rate-limited or locked-out request never reaches the latter at all
— the whole point of checking first is that a "too many attempts"
response can never be timed or shaped by which order number was guessed,
because no query for that order ever runs.

Both rate-limiting tiers are windowed ``COUNT`` queries against
``OrderTrackingAttempt`` — a self-expiring sliding window, not a cache
entry with its own TTL to manage separately. This is a deliberate choice,
not just "whatever was easiest": Django's database cache backend
(``config/settings/base.py`` — no Redis, per CLAUDE.md) implements
``cache.incr()`` as a plain get-then-set with no row lock, which races
under concurrent requests from the same IP — an acceptable imprecision
for a lot of things in this codebase, but not for the one control this
stage exists to build correctly. A ``COUNT`` against real rows has the
same theoretical check-then-insert race in principle, but the actual
window for two requests from one IP landing in the same instant is far
narrower in practice, and the consequence — a few extra guesses let
through on rare timing — is bounded and non-catastrophic, unlike Stage
4's stock-oversell scenario.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.http import HttpRequest
from django.utils import timezone

from core import ratelimit as core_ratelimit
from core.phone import normalize_pk_mobile

from .models import Order, OrderTrackingAttempt
from .tracking_config import (
    TRACKING_LOCKOUT_FAILURE_THRESHOLD,
    TRACKING_LOCKOUT_WINDOW_SECONDS,
    TRACKING_RATE_LIMIT_MAX_ATTEMPTS,
    TRACKING_RATE_LIMIT_WINDOW_SECONDS,
)

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    """Short-window throttle tripped — too many attempts (successful or
    not) from this IP within ``TRACKING_RATE_LIMIT_WINDOW_SECONDS``."""


class LockedOutError(Exception):
    """Escalated lockout — too many *failed* attempts from this IP within
    ``TRACKING_LOCKOUT_WINDOW_SECONDS``. Self-expires as old failures age
    out of the window; there is no separate lockout flag to clear."""


def client_ip(request: HttpRequest) -> str:
    """Delegates to ``core.ratelimit.client_ip`` — see that function for
    the full reasoning (``REMOTE_ADDR`` by default; a trusted
    ``X-Forwarded-For`` in production only, resolved by Stage 13). Kept
    as its own import path since every caller in this module already
    goes through ``tracking.client_ip``, not ``core.ratelimit`` directly.
    """
    return core_ratelimit.client_ip(request)


def check_rate_limit(*, ip_address: str) -> None:
    """Raises before any order lookup happens — see this module's own
    docstring for why the ordering matters, not just the outcome."""
    now = timezone.now()

    lockout_window_start = now - timedelta(seconds=TRACKING_LOCKOUT_WINDOW_SECONDS)
    recent_failures = OrderTrackingAttempt.objects.filter(
        ip_address=ip_address, succeeded=False, created_at__gte=lockout_window_start
    ).count()
    if recent_failures >= TRACKING_LOCKOUT_FAILURE_THRESHOLD:
        raise LockedOutError

    rate_window_start = now - timedelta(seconds=TRACKING_RATE_LIMIT_WINDOW_SECONDS)
    recent_attempts = OrderTrackingAttempt.objects.filter(
        ip_address=ip_address, created_at__gte=rate_window_start
    ).count()
    if recent_attempts >= TRACKING_RATE_LIMIT_MAX_ATTEMPTS:
        raise RateLimitedError


def lookup_order(*, order_number: str, raw_mobile_number: str) -> Order | None:
    """Both the order number and phone must match — every other outcome
    (the order doesn't exist, the phone doesn't match, the phone doesn't
    even parse as a Pakistani mobile number) returns ``None``,
    indistinguishable from the caller's perspective. This single
    collapsed return value is what makes gate 1 (byte-identical "not
    found" and "phone doesn't match" responses) true by construction —
    the view has exactly one failure branch to render, not two templates
    that happen to render the same text today and could drift apart
    later.
    """
    normalized_mobile = normalize_pk_mobile(raw_mobile_number)
    if normalized_mobile is None:
        return None

    try:
        order = Order.objects.prefetch_related("items", "status_events").get(
            order_number=order_number.strip().upper()
        )
    except Order.DoesNotExist:
        return None

    if order.customer_phone != normalized_mobile:
        return None
    return order


def record_attempt(*, ip_address: str, order_number: str, succeeded: bool) -> None:
    OrderTrackingAttempt.objects.create(
        ip_address=ip_address, order_number=order_number.strip().upper(), succeeded=succeeded
    )
    if not succeeded:
        logger.warning(
            "Failed order-tracking lookup from %s for order number %r.", ip_address, order_number
        )
