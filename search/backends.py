"""Search backend abstraction (§15) — ``SearchBackend`` protocol,
``PostgresSearchBackend`` its one implementation, selected by
``settings.SEARCH_BACKEND`` via ``get_search_backend()``. Mirrors the
``DeliveryCalculator``/``NotificationChannel``/``PaymentProvider`` pattern
elsewhere in this project: a future non-Postgres backend drops in behind
the same protocol without touching view code (Stage 5 gate 5 — no view may
import ``PostgresSearchBackend`` directly).

Query shape, verified against real Postgres before being written here (not
assumed from the ORM API alone):

- The tsvector match must be expressed as ``.annotate(search=vector)
  .filter(search=ts_query)`` (Django's ``@@`` translation), never
  ``.filter(rank__gt=0)`` on a ``SearchRank`` annotation — the latter forces
  ``ts_rank`` into the WHERE clause, which the planner cannot satisfy from
  the GIN index, producing a full sequential scan. Confirmed via
  ``QuerySet.explain()`` against a 3,000-row fixture: the ``@@`` form used
  ``Bitmap Index Scan on product_search_tsv_gin``; the ``rank__gt=0`` form
  used ``Seq Scan``. ``SearchRank`` is for ``order_by`` only.
- Combining the tsvector ``@@`` match and the trigram ``%>`` match with
  ``Q(...) | Q(...)``, under a ``LIMIT``, produces a ``BitmapOr`` across
  both GIN indexes — confirmed for the exact-match, typo, and
  short-single-word cases. Neither mechanism alone covers all six §15.1
  cases: tsvector's lexeme boundaries can't match a typo or a fragment of a
  hyphenated SKU, and trigram alone (in isolated, unlimited-query EXPLAINs
  on the same fixture) doesn't always look cheaper than a sequential scan
  to the planner at moderate row counts — the ``LIMIT`` clause is what
  tips the combined query back to the indexed plan, matching how
  ``search()`` is actually called.
"""

from __future__ import annotations

from typing import Protocol

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q, QuerySet
from django.utils.module_loading import import_string

from catalog.models import Product
from core.config import SEARCH_RESULTS_LIMIT, SEARCH_SUGGESTIONS_LIMIT, SEARCH_TSVECTOR_CONFIG


class SearchBackend(Protocol):
    """One concrete implementation exists (``PostgresSearchBackend``); this
    protocol exists so a future non-Postgres backend can drop in behind
    ``settings.SEARCH_BACKEND`` without any view-layer change."""

    def search(self, query: str, *, limit: int = SEARCH_RESULTS_LIMIT) -> QuerySet[Product]:
        """Full, typo- and reorder-tolerant search for a results page."""
        ...

    def suggest(self, query: str, *, limit: int = SEARCH_SUGGESTIONS_LIMIT) -> QuerySet[Product]:
        """Cheap, prefix-based matches for a live type-ahead box."""
        ...


class PostgresSearchBackend:
    """Blends Postgres full-text search (``ts_rank``) with trigram
    word-similarity (``%>``) — see this module's docstring for why both
    are needed and the exact query shape each requires to stay
    index-backed."""

    def search(self, query: str, *, limit: int = SEARCH_RESULTS_LIMIT) -> QuerySet[Product]:
        normalized = query.strip().lower()
        if not normalized:
            return Product.objects.none()

        vector = SearchVector("search_text", config=SEARCH_TSVECTOR_CONFIG)
        ts_query = SearchQuery(normalized, config=SEARCH_TSVECTOR_CONFIG)
        return (
            Product.objects.filter(status=Product.Status.PUBLISHED)
            .annotate(search=vector, rank=SearchRank(vector, ts_query))
            .filter(Q(search=ts_query) | Q(search_text__trigram_word_similar=normalized))
            .order_by("-rank", "-created_at")[:limit]
        )

    def suggest(self, query: str, *, limit: int = SEARCH_SUGGESTIONS_LIMIT) -> QuerySet[Product]:
        normalized = query.strip().lower()
        if not normalized:
            return Product.objects.none()

        return Product.objects.filter(
            status=Product.Status.PUBLISHED, search_text__icontains=normalized
        ).order_by("name")[:limit]


def get_search_backend() -> SearchBackend:
    """Resolves ``settings.SEARCH_BACKEND`` fresh on every call — the
    backend is stateless, so there's nothing worth caching, and re-resolving
    keeps ``override_settings(SEARCH_BACKEND=...)`` in tests honest."""
    from django.conf import settings

    backend_class = import_string(settings.SEARCH_BACKEND)
    return backend_class()  # type: ignore[no-any-return]
