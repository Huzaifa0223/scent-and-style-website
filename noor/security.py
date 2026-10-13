"""Bearer-token protection for the private tablet sync API (``/api/kiosk/sync/``).

The only client is the native Android tablet app, so these endpoints carry no
CORS headers at all and ``OPTIONS`` is not special-cased: a browser page on
another origin can neither preflight nor read a response. (CORS belongs only
to the two public feeds — see ``http.public_feed``.)

Request pipeline, in this order and for every endpoint:

1. HTTPS only outside ``DEBUG``. In production ``SECURE_SSL_REDIRECT`` has
   already redirected plain HTTP before a view runs; this is the backstop
   for a misconfigured front door.
2. Rate limit (~30/min/IP) — *before* the token is checked, so guessing the
   token is throttled just like any other traffic.
3. Token check with ``hmac.compare_digest`` (constant time).
4. Method check, then the view.

Nothing here ever logs or echoes the token or the Authorization header.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from core.ratelimit import RateLimitedError, check_rate_limit, client_ip, record_attempt

from .config import SYNC_RATE_LIMIT_POLICY, SYNC_RATE_LIMIT_SCOPE, SYNC_TOKEN_MIN_LENGTH
from .http import View, error_response

logger = logging.getLogger(__name__)

RATE_LIMIT_RETRY_AFTER_SECONDS = SYNC_RATE_LIMIT_POLICY.window_seconds


def token_matches(request: HttpRequest) -> bool:
    """True only for ``Authorization: Bearer <SCENT_SYNC_TOKEN>``.

    Fails closed: an unset or too-short configured token authorises
    nothing, so a forgotten ``.env`` line cannot open the API.
    """
    expected: str = getattr(settings, "SCENT_SYNC_TOKEN", "")
    if len(expected) < SYNC_TOKEN_MIN_LENGTH:
        return False
    scheme, _, supplied = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    supplied = supplied.strip()
    if scheme.lower() != "bearer" or not supplied:
        return False
    # Bytes, not str: compare_digest raises TypeError on non-ASCII str.
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def kiosk_endpoint(*methods: str) -> Callable[[View], View]:
    """Wrap a view in the pipeline above, allowing only ``methods``."""

    def decorator(view: View) -> View:
        @wraps(view)
        def wrapper(request: HttpRequest) -> HttpResponse:
            if not settings.DEBUG and not request.is_secure():
                return _finish(error_response(403, "https_required"))

            ip_address = client_ip(request)
            try:
                check_rate_limit(
                    scope=SYNC_RATE_LIMIT_SCOPE,
                    ip_address=ip_address,
                    policy=SYNC_RATE_LIMIT_POLICY,
                )
            except RateLimitedError:
                response = error_response(429, "rate_limited")
                response["Retry-After"] = str(RATE_LIMIT_RETRY_AFTER_SECONDS)
                return _finish(response)

            authorised = token_matches(request)
            record_attempt(scope=SYNC_RATE_LIMIT_SCOPE, ip_address=ip_address, succeeded=authorised)
            if not authorised:
                response = error_response(401, "unauthorised")
                response["WWW-Authenticate"] = "Bearer"
                return _finish(response)

            if request.method not in methods:
                response = error_response(405, "method_not_allowed")
                response["Allow"] = ", ".join(methods)
                return _finish(response)

            return _finish(view(request))

        # Token API: no cookies, no session — CSRF does not apply.
        return csrf_exempt(wrapper)

    return decorator


def _finish(response: HttpResponse) -> HttpResponse:
    """Private data must never sit in a shared cache."""
    response["Cache-Control"] = "private, no-store"
    return response
