"""PostgresSearchBackend against the six §15.1 cases — Stage 5 gate 1.

Written and watched to fail (ModuleNotFoundError: no search.backends
module) before search/backends.py existed, per the roadmap's explicit
"write the table as tests first" instruction. All six share one fixture: a
single target product real customers would plausibly search for with any
of these six queries, plus decoy products that must NOT match, so a test
that only checked "something came back" couldn't pass by accident.
"""

from __future__ import annotations

import pytest

from catalog.factories import ProductFactory, ProductVariantFactory
from catalog.models import Product
from search.backends import PostgresSearchBackend


@pytest.fixture
def target_product():  # type: ignore[no-untyped-def]
    product = ProductFactory(name="Afnan 9PM Eau de Parfum", status=Product.Status.PUBLISHED)
    product.variants.update(sku="EDP-9PM-100")
    ProductVariantFactory(product=product, sku="EDP-9PM-100-50ML")
    product.refresh_from_db()
    return product


@pytest.fixture(autouse=True)
def _decoy_products(db):  # type: ignore[no-untyped-def]
    """Unrelated products sharing no vocabulary with the target — proves a
    match is genuinely about relevance, not "everything comes back"."""
    ProductFactory(name="Wireless Running Sneaker", status=Product.Status.PUBLISHED)
    ProductFactory(name="Leather Office Chair", status=Product.Status.PUBLISHED)
    ProductFactory(name="Organic Cotton Bedsheet", status=Product.Status.PUBLISHED)


@pytest.mark.django_db
def test_exact_multi_word_query_matches(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("afnan 9pm")
    assert target_product in results


@pytest.mark.django_db
def test_short_single_word_query_matches(target_product) -> None:  # type: ignore[no-untyped-def]
    """The `9pm` trap: similarity() fails a 3-character query against a
    long product name — this must go through word_similarity()/%>."""
    results = PostgresSearchBackend().search("9pm")
    assert target_product in results


@pytest.mark.django_db
def test_query_is_case_insensitive(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("AFNAN")
    assert target_product in results


@pytest.mark.django_db
def test_typo_in_query_still_matches(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("afnn")
    assert target_product in results


@pytest.mark.django_db
def test_reordered_query_words_still_match(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("9PM afnan")
    assert target_product in results


@pytest.mark.django_db
def test_partial_sku_query_matches(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("EDP-9PM-100")
    assert target_product in results


@pytest.mark.django_db
def test_unrelated_query_does_not_match(target_product) -> None:  # type: ignore[no-untyped-def]
    results = PostgresSearchBackend().search("bedsheet")
    assert target_product not in results


@pytest.mark.django_db
def test_unpublished_products_are_excluded_even_on_an_exact_match() -> None:
    draft = ProductFactory(name="Afnan 9PM Draft Preview", status=Product.Status.DRAFT)

    results = PostgresSearchBackend().search("afnan 9pm")

    assert draft not in results
