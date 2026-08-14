"""sitemap.xml and robots.txt (§34, roadmap Stage 12 gate 2)."""

from __future__ import annotations

import pytest

from catalog.factories import CategoryFactory, ProductFactory
from catalog.models import Product


@pytest.mark.django_db
def test_gate2_sitemap_includes_every_published_product(client) -> None:  # type: ignore[no-untyped-def]
    published = ProductFactory(status=Product.Status.PUBLISHED)

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    body = response.content.decode()
    assert f"/product/{published.slug}/" in body


@pytest.mark.django_db
def test_gate2_sitemap_excludes_draft_and_archived_products(client) -> None:  # type: ignore[no-untyped-def]
    draft = ProductFactory(status=Product.Status.DRAFT)
    archived = ProductFactory(status=Product.Status.ARCHIVED)

    response = client.get("/sitemap.xml")

    body = response.content.decode()
    assert f"/product/{draft.slug}/" not in body
    assert f"/product/{archived.slug}/" not in body


@pytest.mark.django_db
def test_gate2_sitemap_includes_every_published_category(client) -> None:  # type: ignore[no-untyped-def]
    published = CategoryFactory(is_published=True)

    response = client.get("/sitemap.xml")

    body = response.content.decode()
    assert f"/category/{published.slug}/" in body


@pytest.mark.django_db
def test_gate2_sitemap_excludes_unpublished_categories(client) -> None:  # type: ignore[no-untyped-def]
    unpublished = CategoryFactory(is_published=False)

    response = client.get("/sitemap.xml")

    body = response.content.decode()
    assert f"/category/{unpublished.slug}/" not in body


@pytest.mark.django_db
def test_sitemap_includes_the_static_pages(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/sitemap.xml")

    body = response.content.decode()
    assert "/products/</loc>" in body
    assert "/track/</loc>" in body


@pytest.mark.django_db
def test_robots_txt_disallows_the_portal_and_allows_everything_else(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    assert "Disallow: /admin-portal/" in body
    assert "Disallow: /accounts/" in body
    assert "Allow: /" in body


@pytest.mark.django_db
def test_robots_txt_points_at_the_real_sitemap_url(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/robots.txt")

    body = response.content.decode()
    assert "Sitemap: http://testserver/sitemap.xml" in body
