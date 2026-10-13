"""Public, unauthenticated feeds: /api/noor/catalog.json and products.json."""

from __future__ import annotations

import json
import re

import pytest

from catalog.factories import BrandFactory
from catalog.models import Product
from noor.tests.support import CATALOG_URL, PRODUCTS_URL, published
from store.models import StoreSettings

NOOR_ORIGIN = "https://noor.scentandstyle.pk"
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FEEDS = pytest.mark.parametrize("url", [CATALOG_URL, PRODUCTS_URL])


def _get(client, url):  # type: ignore[no-untyped-def]
    response = client.get(url)
    return response, json.loads(response.content)


@pytest.mark.django_db
def test_catalog_has_exactly_the_documented_shape(client) -> None:  # type: ignore[no-untyped-def]
    product = published("Khamrah", price="8500.00", stock=4)

    response, payload = _get(client, CATALOG_URL)

    assert response.status_code == 200
    assert set(payload) == {"generatedAt", "items"}
    assert ISO_Z.match(payload["generatedAt"])
    assert payload["items"] == [
        {
            "slug": product.slug,
            "price": 8500,
            "inStock": True,
            "url": f"http://testserver/product/{product.slug}/",
        }
    ]


@pytest.mark.django_db
def test_products_feed_has_exactly_the_documented_shape(client) -> None:  # type: ignore[no-untyped-def]
    product = published(
        "Khamrah",
        brand=BrandFactory(name="Lattafa"),
        short_description="Eau de Parfum (EDP) 100ml",
        top_notes="Bergamot",
        heart_notes="Dates",
        base_notes="Vanilla",
    )

    response, payload = _get(client, PRODUCTS_URL)

    assert response.status_code == 200
    assert ISO_Z.match(payload["generatedAt"])
    (item,) = payload["items"]
    assert set(item) == {
        "slug", "name", "brand", "category", "price", "inStock",
        "description", "image", "url", "notes",
    }  # fmt: skip
    assert item["slug"] == product.slug
    assert item["name"] == "Khamrah"
    assert item["brand"] == "Lattafa"
    assert item["price"] == 8500
    assert item["inStock"] is True
    assert item["description"] == "Eau de Parfum (EDP) 100ml"
    assert item["notes"] == {"top": ["Bergamot"], "heart": ["Dates"], "base": ["Vanilla"]}


@pytest.mark.django_db
def test_notes_are_empty_lists_when_the_site_stores_none(client) -> None:  # type: ignore[no-untyped-def]
    published("Plain")

    _, payload = _get(client, PRODUCTS_URL)

    assert payload["items"][0]["notes"] == {"top": [], "heart": [], "base": []}


@pytest.mark.django_db
@FEEDS
def test_only_published_products_are_listed(client, url) -> None:  # type: ignore[no-untyped-def]
    live = published("Live")
    published("Draft", status=Product.Status.DRAFT)
    published("Archived", status=Product.Status.ARCHIVED)

    _, payload = _get(client, url)

    assert [item["slug"] for item in payload["items"]] == [live.slug]


@pytest.mark.django_db
@FEEDS
def test_stock_counts_are_never_published(client, url) -> None:  # type: ignore[no-untyped-def]
    published("Stocked", stock=7)
    published("Sold Out", stock=0)

    response, payload = _get(client, url)

    flags = {item["inStock"] for item in payload["items"]}
    assert flags == {True, False}
    assert all(isinstance(item["inStock"], bool) for item in payload["items"])
    keys = {key for item in payload["items"] for key in item}
    assert not any("qty" in key.lower() or "quantity" in key.lower() for key in keys)
    assert "stockQty" not in response.content.decode()


@pytest.mark.django_db
@FEEDS
def test_nothing_beyond_the_public_product_page_is_exposed(client, url) -> None:  # type: ignore[no-untyped-def]
    published("Khamrah")

    response, _ = _get(client, url)

    body = response.content.decode().lower()
    for private in ("cost", "supplier", "margin", "sku", "compare_at", "reserved", "meta_title"):
        assert private not in body


@pytest.mark.django_db
@FEEDS
def test_get_carries_cors_and_cache_headers(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.get(url)

    assert response["Access-Control-Allow-Origin"] == NOOR_ORIGIN
    assert "Origin" in response["Vary"]
    assert response["Cache-Control"] == "public, max-age=300"
    assert response["Content-Type"].startswith("application/json")


@pytest.mark.django_db
@FEEDS
def test_a_shoppers_session_does_not_fragment_the_cache(client, url) -> None:  # type: ignore[no-untyped-def]
    variant = published(stock=5).variants.get()
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    assert "sessionid" in client.cookies  # a real, live session

    response = client.get(url)

    assert "Cookie" not in response.get("Vary", "")
    assert "Set-Cookie" not in response


@pytest.mark.django_db
@FEEDS
def test_origin_is_fixed_not_echoed(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.get(url, HTTP_ORIGIN="https://evil.example")

    assert response["Access-Control-Allow-Origin"] == NOOR_ORIGIN


@pytest.mark.django_db
@FEEDS
def test_options_preflight_answers_with_cors_and_allow_get(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.options(url, HTTP_ORIGIN=NOOR_ORIGIN)

    assert response.status_code == 204
    assert response["Access-Control-Allow-Origin"] == NOOR_ORIGIN
    assert "Origin" in response["Vary"]
    assert response["Allow"] == "GET"
    assert response["Access-Control-Allow-Methods"] == "GET"
    assert response["Cache-Control"] == "public, max-age=300"
    assert response.content == b""


@pytest.mark.django_db
@FEEDS
def test_other_methods_are_rejected(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.post(url, {})

    assert response.status_code == 405
    assert response["Allow"] == "GET"


@pytest.mark.django_db
@FEEDS
def test_no_token_is_needed(client, url) -> None:  # type: ignore[no-untyped-def]
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_urls_use_the_configured_site_url_when_set(client) -> None:  # type: ignore[no-untyped-def]
    store = StoreSettings.load()
    store.site_url = "https://scentandstyle.pk/"
    store.save()
    product = published()

    _, payload = _get(client, CATALOG_URL)

    assert payload["items"][0]["url"] == f"https://scentandstyle.pk/product/{product.slug}/"


@pytest.mark.django_db
def test_empty_catalog_is_a_valid_empty_list(client) -> None:  # type: ignore[no-untyped-def]
    response, payload = _get(client, CATALOG_URL)

    assert response.status_code == 200
    assert payload["items"] == []
