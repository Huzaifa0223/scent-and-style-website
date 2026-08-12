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

from search.backends import get_search_backend


class SearchSuggestView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        query = request.GET.get("q", "").strip()
        products = get_search_backend().suggest(query)
        return render(request, "search/_suggestions.html", {"products": products, "query": query})
