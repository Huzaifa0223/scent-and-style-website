"""SearchSuggestView — the HTMX type-ahead endpoint (§15). Stage 5 gate 5
(no view imports PostgresSearchBackend directly) lives here too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from catalog.factories import ProductFactory
from catalog.models import Product


def _imports_postgres_search_backend(py_file: Path) -> bool:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == "PostgresSearchBackend" for alias in node.names
        ):
            return True
    return False


@pytest.mark.django_db
def test_suggest_returns_matching_products(client) -> None:  # type: ignore[no-untyped-def]
    ProductFactory(name="Afnan 9PM Eau de Parfum", status=Product.Status.PUBLISHED)
    ProductFactory(name="Unrelated Sneaker", status=Product.Status.PUBLISHED)

    response = client.get("/search/suggest/", {"q": "afnan"})

    assert response.status_code == 200
    assert b"Afnan 9PM Eau de Parfum" in response.content
    assert b"Unrelated Sneaker" not in response.content


@pytest.mark.django_db
def test_suggest_rows_link_to_the_storefront_pdp(client) -> None:  # type: ignore[no-untyped-def]
    product = ProductFactory(name="Afnan 9PM Eau de Parfum", status=Product.Status.PUBLISHED)

    response = client.get("/search/suggest/", {"q": "afnan"})

    assert f"/product/{product.slug}/".encode() in response.content


@pytest.mark.django_db
def test_suggest_with_an_empty_query_returns_no_results_without_erroring(client) -> None:  # type: ignore[no-untyped-def]
    ProductFactory(name="Afnan 9PM Eau de Parfum", status=Product.Status.PUBLISHED)

    response = client.get("/search/suggest/", {"q": ""})

    assert response.status_code == 200
    assert b"Afnan 9PM Eau de Parfum" not in response.content


@pytest.mark.django_db
def test_suggest_excludes_unpublished_products(client) -> None:  # type: ignore[no-untyped-def]
    ProductFactory(name="Draft Afnan Product", status=Product.Status.DRAFT)

    response = client.get("/search/suggest/", {"q": "afnan"})

    assert response.status_code == 200
    assert b"Draft Afnan Product" not in response.content


@pytest.mark.django_db
def test_suggest_rejects_post() -> None:
    from django.test import Client

    response = Client().post("/search/suggest/", {"q": "afnan"})

    assert response.status_code == 405


def test_no_view_module_imports_postgressearchbackend_directly() -> None:
    """Stage 5 gate 5 — every access to search must go through
    get_search_backend(), never the concrete class."""
    project_root = Path(__file__).resolve().parents[2]
    offenders = []
    for py_file in project_root.rglob("*views.py"):
        if ".venv" in py_file.parts or "tests" in py_file.parts or py_file.name.startswith("test_"):
            continue
        if _imports_postgres_search_backend(py_file):
            offenders.append(str(py_file))
    assert offenders == [], f"views importing PostgresSearchBackend directly: {offenders}"
