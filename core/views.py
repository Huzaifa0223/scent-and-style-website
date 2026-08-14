from __future__ import annotations

from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse


def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness/readiness probe.

    No auth, no PII, no version string (CLAUDE.md/roadmap Stage 1) — this
    endpoint is reachable by anything that can reach the server at all,
    including uptime monitors sitting outside any auth boundary.
    """
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        db_ok = False

    return JsonResponse(
        {"status": "ok" if db_ok else "error", "database": db_ok},
        status=200 if db_ok else 503,
    )


def robots_txt(request: HttpRequest) -> HttpResponse:
    """§34. Disallows the merchant portal, auth, cart, and checkout —
    none of those are content a search engine should index (portal/auth
    for the obvious reason; cart/checkout because they're session-
    specific and never the same page twice, pure crawl-budget waste).
    ``/track/`` is deliberately *not* disallowed — the bare lookup form
    is a legitimate, useful page to index.
    """
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))
    return render(request, "robots.txt", {"sitemap_url": sitemap_url}, content_type="text/plain")
