"""The rebuild_search_index management command (§15) — Stage 5 gate 3:
idempotent, and reports a count.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from catalog.factories import ProductFactory
from catalog.models import Product


@pytest.mark.django_db
def test_command_reports_the_total_product_count() -> None:
    # search_text is already correct at creation time (catalog/signals.py
    # populates it live), so a run right after creation legitimately
    # recomputes zero — this checks the total, not the recomputed count.
    ProductFactory(name="First Product")
    ProductFactory(name="Second Product")

    out = StringIO()
    call_command("rebuild_search_index", stdout=out)

    assert "of 2 product(s)." in out.getvalue()


@pytest.mark.django_db
def test_command_recomputes_search_text_bypassed_by_a_raw_update() -> None:
    """Simulates a path that skips the ORM's save() (and therefore
    catalog/signals.py) — a raw .update() call, standing in for a bulk
    import or manual data fix."""
    product = ProductFactory(name="Stale Product")
    Product.objects.filter(pk=product.pk).update(search_text="")
    product.refresh_from_db()
    assert product.search_text == ""

    call_command("rebuild_search_index", stdout=StringIO())

    product.refresh_from_db()
    assert "stale product" in product.search_text


@pytest.mark.django_db
def test_command_is_idempotent_a_second_run_recomputes_nothing() -> None:
    ProductFactory(name="Idempotent Product")
    call_command("rebuild_search_index", stdout=StringIO())

    out = StringIO()
    call_command("rebuild_search_index", stdout=out)

    assert "Rebuilt search_text for 0 of 1 product(s)." in out.getvalue()


@pytest.mark.django_db
def test_command_reports_zero_of_zero_with_an_empty_catalog() -> None:
    out = StringIO()
    call_command("rebuild_search_index", stdout=out)
    assert "Rebuilt search_text for 0 of 0 product(s)." in out.getvalue()
