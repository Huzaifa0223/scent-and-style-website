"""HTMX type-ahead endpoint (§15). GET-only (no ``post()``, so ``View``'s
own dispatch rejects other methods with 405 — the same mechanism used for
every mutation endpoint elsewhere in this project, just read-only here).

Goes through ``get_search_backend()``, never ``PostgresSearchBackend``
directly — Stage 5 gate 5.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic import View

from core import ratelimit
from core.models import RateLimitScope
from core.ratelimit import SEARCH_RATE_LIMIT_POLICY
from search.backends import get_search_backend


class SearchSuggestView(View):
    """§41: "rate limiting on... search". This is a type-ahead endpoint
    hit on every keystroke, so its policy (``SEARCH_RATE_LIMIT_POLICY``)
    has no lockout tier — there is no notion of a "failed" search to
    escalate on, only a raw per-minute request cap.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        ip_address = ratelimit.client_ip(request)
        try:
            ratelimit.check_rate_limit(
                scope=RateLimitScope.SEARCH, ip_address=ip_address, policy=SEARCH_RATE_LIMIT_POLICY
            )
        except ratelimit.RateLimitedError:
            return render(
                request,
                "search/_suggestions.html",
                {"products": [], "query": "", "rate_limited": True},
                status=429,
            )

        query = request.GET.get("q", "").strip()
        products = get_search_backend().suggest(query)
        ratelimit.record_attempt(scope=RateLimitScope.SEARCH, ip_address=ip_address, succeeded=True)
        return render(request, "search/_suggestions.html", {"products": products, "query": query})
