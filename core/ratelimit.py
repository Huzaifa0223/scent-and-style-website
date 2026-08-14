"""Shared rate limiter for login, checkout, and search (§41, roadmap
Stage 13). See ``core.models.RateLimitAttempt`` for why this is a DB
table rather than a cache counter, and why order tracking (§25, Stage 11)
keeps its own separate mechanism instead of moving onto this one.

Every caller follows the same shape ``orders.tracking`` established:
check the limit *before* doing any real work, record the outcome
afterward. A rate-limited or locked-out request should never reach the
expensive/sensitive path it's guarding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

from .models import RateLimitAttempt, RateLimitScope

logger = logging.getLogger(__name__)


class RateLimitedError(Exception):
    """Short-window throttle tripped — too many attempts (successful or
    not) from this IP within the policy's ``window_seconds``."""


class LockedOutError(Exception):
    """Escalated lockout — too many *failed* attempts from this IP within
    the policy's ``lockout_window_seconds``. Only raised when the policy
    defines a lockout tier at all; see ``RateLimitPolicy``."""


@dataclass(frozen=True)
class RateLimitPolicy:
    """Thresholds for one scope. ``lockout_failure_threshold`` is
    optional: search has no meaningful notion of a "failed" request, so
    its policy omits the lockout tier entirely rather than setting an
    arbitrarily high threshold to fake disabling it.
    """

    max_attempts: int
    window_seconds: int
    lockout_failure_threshold: int | None = None
    lockout_window_seconds: int = 0


def client_ip(request: HttpRequest) -> str:
    """The IP address every rate limiter in this project keys its budget
    on — ``orders.tracking.client_ip`` delegates here too (Stage 13
    generalised what was, through Stage 11, an order-tracking-only
    concern; see that module for why it keeps its own separate
    *attempt-tracking* mechanism even though it now shares this one
    function).

    ``REMOTE_ADDR`` by default. In production
    (``settings.TRUST_X_FORWARDED_FOR``, set only by
    ``config.settings.prod``) the last entry of ``X-Forwarded-For`` is
    trusted instead — safe specifically because Caddy is the *only*
    process gunicorn accepts connections from (docs/deploy.md), so
    that header has exactly one trusted hop appending the real client
    address, not an arbitrary, spoofable proxy chain. Outside that
    setting (dev, test), honouring a client-supplied header would let a
    request simply claim a different rate-limit identity for itself.
    """
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded_for: str = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            last_hop: str = forwarded_for.split(",")[-1].strip()
            return last_hop
    ip_address: str = request.META.get("REMOTE_ADDR", "")
    return ip_address


def check_rate_limit(*, scope: RateLimitScope, ip_address: str, policy: RateLimitPolicy) -> None:
    """Raises before the caller does any real work — see this module's
    own docstring for why the ordering matters, not just the outcome."""
    now = timezone.now()

    if policy.lockout_failure_threshold is not None:
        lockout_window_start = now - timedelta(seconds=policy.lockout_window_seconds)
        recent_failures = RateLimitAttempt.objects.filter(
            scope=scope,
            ip_address=ip_address,
            succeeded=False,
            created_at__gte=lockout_window_start,
        ).count()
        if recent_failures >= policy.lockout_failure_threshold:
            raise LockedOutError

    window_start = now - timedelta(seconds=policy.window_seconds)
    recent_attempts = RateLimitAttempt.objects.filter(
        scope=scope, ip_address=ip_address, created_at__gte=window_start
    ).count()
    if recent_attempts >= policy.max_attempts:
        raise RateLimitedError


def record_attempt(*, scope: RateLimitScope, ip_address: str, succeeded: bool) -> None:
    RateLimitAttempt.objects.create(scope=scope, ip_address=ip_address, succeeded=succeeded)
    if not succeeded:
        logger.warning("Failed %s attempt from %s.", scope, ip_address)


# Named policies, one per scope. Colocated with RateLimitPolicy itself
# rather than in core/config.py: that module is deliberately dependency-
# free scalar constants (importable before Django's app registry is
# ready), and a dataclass keyed to RateLimitScope belongs next to the
# type it configures.
#
# "A small number of attempts per minute" (§41) for login and checkout —
# both are meaningfully "failable" (wrong password; a validation error or
# a race on the last unit of stock), so both get a lockout tier too.
# Search has no comparable failure concept (every query "succeeds"), so
# SEARCH_RATE_LIMIT_POLICY defines only the short-window throttle.
LOGIN_RATE_LIMIT_POLICY: Final = RateLimitPolicy(
    max_attempts=5,
    window_seconds=60,
    lockout_failure_threshold=10,
    lockout_window_seconds=3600,
)
CHECKOUT_RATE_LIMIT_POLICY: Final = RateLimitPolicy(
    max_attempts=10,
    window_seconds=60,
    lockout_failure_threshold=20,
    lockout_window_seconds=3600,
)
SEARCH_RATE_LIMIT_POLICY: Final = RateLimitPolicy(max_attempts=30, window_seconds=60)
