"""Recomputes Product.search_text for every product (§15) — a full resync,
distinct from catalog/signals.py's per-save incremental updates. Run
on-demand, not on a schedule — unlike inventory's sweeper, nothing in this
project currently needs it to run periodically.

When this is needed even though the signals exist: an AttributeDefinition's
is_filterable flag changes after the fact (nothing re-saves the products
that use it), or a bulk import writes rows through a path that bypasses the
ORM's save()/delete() (raw SQL, a future CSV import using bulk_create).
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand

from catalog.models import Product
from catalog.search_indexing import rebuild_search_text

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recompute search_text for every product."

    def handle(self, *args: Any, **options: Any) -> None:
        total = 0
        updated = 0
        queryset = Product.objects.select_related("category", "brand", "subcategory").iterator()
        for product in queryset:
            total += 1
            if rebuild_search_text(product):
                updated += 1
        logger.info("rebuild_search_index: recomputed %d of %d product(s)", updated, total)
        self.stdout.write(f"Rebuilt search_text for {updated} of {total} product(s).")
