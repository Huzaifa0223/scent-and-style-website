"""Stage 5 gate 4: search across a 1,000-product fixture returns inside an
asserted time bound, and EXPLAIN confirms a GIN index is used rather than
a sequential scan.

The fixture is deliberately varied (a brand/noun/adjective/random-SKU
combinatorial generator), not 1,000 rows of repeated boilerplate text —
that's what turned up this gate's real trap (see catalog/models.py's GIN
index comments and specs/state.md's Stage 5 notes): GIN indexes default to
``fastupdate=on``, so a bulk insert lands in an unordered "pending list"
that only ``VACUUM`` flushes, not ``ANALYZE`` — until it's flushed, the
planner correctly prices a bitmap index scan as more expensive than a
sequential scan and picks the sequential scan, with no error. Both GIN
indexes are declared with ``fastupdate=False`` specifically so this test
(and, more importantly, production search right after a catalog import)
doesn't depend on autovacuum's timing.
"""

from __future__ import annotations

import random
import string
import time
from decimal import Decimal

import pytest
from django.db import connection, transaction

from catalog.factories import CategoryFactory
from catalog.models import Product, ProductVariant
from search.backends import PostgresSearchBackend

GATE_4_FIXTURE_SIZE = 1000

GATE_4_TIME_BUDGET_SECONDS = 1.0
"""Generous on purpose — a GIN-index-backed query over this fixture size
runs in low milliseconds. The bound exists to catch a regression back to a
sequential scan, not to pin down exact latency; the EXPLAIN assertion below
is what actually proves the index is used."""

# "Afnan" excluded — it's the target product's own brand (below); keeping
# it out of the decoy vocabulary keeps the fixture easy to reason about.
_BRANDS = [
    "Nike",
    "Adidas",
    "Sony",
    "Apple",
    "Samsung",
    "Dior",
    "Chanel",
    "Puma",
    "Reebok",
    "Zara",
    "Gucci",
    "Prada",
    "Rolex",
    "Casio",
    "Seiko",
    "Bose",
    "JBL",
    "Anker",
    "Levi's",
]
_NOUNS = [
    "Perfume",
    "Sneaker",
    "Shoe",
    "Watch",
    "Bag",
    "Jacket",
    "Shirt",
    "Earbuds",
    "Charger",
    "Speaker",
    "Wallet",
    "Belt",
    "Sunglasses",
    "Backpack",
    "Hoodie",
    "Cap",
    "Scarf",
    "Gloves",
]
_ADJECTIVES = [
    "Wireless",
    "Leather",
    "Organic",
    "Premium",
    "Classic",
    "Sport",
    "Limited",
    "Vintage",
    "Slim",
    "Compact",
    "Deluxe",
    "Eco",
    "Pro",
    "Max",
    "Mini",
    "Ultra",
]


def _random_sku() -> str:
    return "-".join(
        "".join(random.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(3)
    )


@pytest.fixture
def large_fixture(db):  # type: ignore[no-untyped-def]
    """1,000 varied published products, plus one target product a customer
    would plausibly search for with a typo or a partial SKU — the same
    shape as the six §15.1 cases, at realistic scale."""
    category = CategoryFactory()
    with transaction.atomic():
        products = []
        for i in range(GATE_4_FIXTURE_SIZE):
            brand = random.choice(_BRANDS)
            noun = random.choice(_NOUNS)
            adj = random.choice(_ADJECTIVES)
            sku = _random_sku()
            products.append(
                Product(
                    name=f"{brand} {adj} {noun} {i}",
                    slug=f"gate4-product-{i}",
                    category=category,
                    status=Product.Status.PUBLISHED,
                    search_text=f"{brand} {noun} {adj} {sku}".lower(),
                )
            )
        Product.objects.bulk_create(products, batch_size=500)
        created = list(Product.objects.filter(category=category).order_by("id"))
        variants = [
            ProductVariant(
                product=p, sku=f"GATE4-SKU-{p.id}", price=Decimal("10.00"), stock_quantity=5
            )
            for p in created
        ]
        ProductVariant.objects.bulk_create(variants, batch_size=500)

    # created[0]'s variant was bulk_create'd, which bypasses post_save (no
    # signal fires); its SKU must be updated *before* the product's own
    # save() below, or the signal's recompute would still read the old
    # bulk-created SKU value.
    target = created[0]
    target.variants.update(sku="EDP-9PM-100-50ML")
    target.name = "Afnan 9PM Eau de Parfum"
    target.save(update_fields=["name", "updated_at"])
    target.refresh_from_db()

    with connection.cursor() as cursor:
        cursor.execute("ANALYZE catalog_product")

    return target


@pytest.mark.django_db
def test_gate4_search_over_1000_products_is_fast_and_uses_the_gin_index(
    large_fixture,  # type: ignore[no-untyped-def]
) -> None:
    backend = PostgresSearchBackend()

    started = time.perf_counter()
    results = list(backend.search("afnan 9pm"))
    elapsed = time.perf_counter() - started

    assert large_fixture in results
    assert elapsed < GATE_4_TIME_BUDGET_SECONDS, (
        f"search() took {elapsed:.3f}s over {GATE_4_FIXTURE_SIZE} products, "
        f"budget is {GATE_4_TIME_BUDGET_SECONDS}s"
    )

    plan = backend.search("afnan 9pm").explain()
    assert "Seq Scan" not in plan, f"expected an index scan, got:\n{plan}"
    assert "product_search_tsv_gin" in plan or "product_search_trgm_gin" in plan, (
        f"expected a GIN index in the plan, got:\n{plan}"
    )
