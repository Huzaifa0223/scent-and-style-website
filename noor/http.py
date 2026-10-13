"""Response helpers shared by the public feeds and the private sync API."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.cache import patch_vary_headers

from .config import PREFLIGHT_MAX_AGE_SECONDS, PUBLIC_FEED_MAX_AGE_SECONDS

View = Callable[[HttpRequest], HttpResponse]

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


def iso_utc(moment: datetime) -> str:
    """``2026-10-13T09:30:00Z`` — the format Noor's contract documents."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def json_response(data: dict[str, Any], *, status: int = 200) -> JsonResponse:
    # ensure_ascii=False: product names may be Urdu; the charset is declared.
    return JsonResponse(
        data,
        status=status,
        content_type=JSON_CONTENT_TYPE,
        json_dumps_params={"ensure_ascii": False},
    )


def error_response(status: int, code: str) -> JsonResponse:
    return json_response({"error": code}, status=status)


def add_cors(response: HttpResponse) -> HttpResponse:
    """Allow exactly one browser origin — never echoed from the request, never
    ``*``. ``Vary: Origin`` keeps a shared cache from handing one origin's
    answer to another."""
    response["Access-Control-Allow-Origin"] = settings.NOOR_ORIGIN
    patch_vary_headers(response, ("Origin",))
    return response


def preflight(
    methods: tuple[str, ...], *, allow_headers: str = "", public_cache: bool = False
) -> HttpResponse:
    response = HttpResponse(status=204)
    add_cors(response)
    response["Allow"] = ", ".join(methods)
    response["Access-Control-Allow-Methods"] = ", ".join(methods)
    if allow_headers:
        response["Access-Control-Allow-Headers"] = allow_headers
    response["Access-Control-Max-Age"] = str(PREFLIGHT_MAX_AGE_SECONDS)
    if public_cache:
        response["Cache-Control"] = f"public, max-age={PUBLIC_FEED_MAX_AGE_SECONDS}"
    return response


def public_feed(view: View) -> View:
    """Read-only, unauthenticated, cross-origin-readable by Noor's origin.

    Never touches the session or the user, so nothing adds ``Vary: Cookie``
    and a shared cache may reuse the response for every visitor.
    """

    @wraps(view)
    def wrapper(request: HttpRequest) -> HttpResponse:
        if request.method == "OPTIONS":
            return preflight(("GET",), public_cache=True)
        if request.method not in ("GET", "HEAD"):
            rejection = error_response(405, "method_not_allowed")
            rejection["Allow"] = "GET"
            return add_cors(rejection)
        response = view(request)
        response["Cache-Control"] = f"public, max-age={PUBLIC_FEED_MAX_AGE_SECONDS}"
        return add_cors(response)

    return wrapper
