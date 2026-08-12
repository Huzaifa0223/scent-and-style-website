from __future__ import annotations

from django.db import connection
from django.db.utils import Error as DatabaseError
from django.http import HttpRequest, JsonResponse


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
