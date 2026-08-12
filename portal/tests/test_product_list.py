from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.factories import BrandFactory, CategoryFactory, ProductFactory
from catalog.models import Product

LIST_URL = "/admin-portal/products/"


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(LIST_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_authenticated_user_without_permission_is_denied(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Django's exception-to-response middleware converts the raised
    PermissionDenied into a real 403 response for a request that goes
    through the full stack (unlike accounts/tests/test_mixins.py's
    RequestFactory-based unit tests, which call the view directly and see
    the raised exception itself)."""
    user = django_user_model.objects.create_user(username="nobody", password="x")
    client.force_login(user)
    response = client.get(LIST_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_sees_the_list(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    product = ProductFactory(name="Afnan 9PM")
    response = client.get(LIST_URL)
    assert response.status_code == 200
    assert product.name.encode() in response.content


@pytest.mark.django_db
def test_search_matches_product_name(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    ProductFactory(name="Afnan 9PM")
    ProductFactory(name="Something Else")

    response = client.get(LIST_URL, {"q": "9PM"})

    assert b"Afnan 9PM" in response.content
    assert b"Something Else" not in response.content


@pytest.mark.django_db
def test_search_matches_variant_sku_without_duplicating_rows(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Exercises the Exists()-based SKU search — a join-based
    filter(variants__sku__icontains=...) would fan the product row out
    once per matching variant."""
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    ProductFactory(name="Afnan 9PM", default_variant_sku="AFNAN-9PM-UNIQUE")

    response = client.get(LIST_URL, {"q": "9PM-UNIQUE"})

    assert response.content.count(b"Afnan 9PM") == 1


@pytest.mark.django_db
def test_filter_by_status(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    ProductFactory(name="Draft Product", status=Product.Status.DRAFT)
    ProductFactory(name="Published Product", status=Product.Status.PUBLISHED)

    response = client.get(LIST_URL, {"status": "published"})

    assert b"Published Product" in response.content
    assert b"Draft Product" not in response.content


@pytest.mark.django_db
def test_filter_by_category(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    category_a = CategoryFactory(name="Category A")
    category_b = CategoryFactory(name="Category B")
    ProductFactory(name="In A", category=category_a)
    ProductFactory(name="In B", category=category_b)

    response = client.get(LIST_URL, {"category": category_a.slug})

    assert b"In A" in response.content
    assert b"In B" not in response.content


@pytest.mark.django_db
def test_filter_by_brand(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    brand_a = BrandFactory(name="Brand A")
    brand_b = BrandFactory(name="Brand B")
    ProductFactory(name="From A", brand=brand_a)
    ProductFactory(name="From B", brand=brand_b)

    response = client.get(LIST_URL, {"brand": brand_a.slug})

    assert b"From A" in response.content
    assert b"From B" not in response.content


@pytest.mark.django_db
def test_display_price_shown_for_active_variant(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    ProductFactory(name="Priced Product", default_variant_price=Decimal("1500.00"))

    response = client.get(LIST_URL)

    assert b"1,500.00" in response.content


@pytest.mark.django_db
def test_query_count_stays_flat_as_fixture_count_grows_from_5_to_50(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Acceptance gate 5. Compares actual captured query counts rather than
    asserting a hardcoded number — the point is flatness, not a specific
    figure, and page 1 genuinely shows a different number of rows in each
    run (5 fixtures all fit on one page of 25; 50 fixtures fill the whole
    page), so an N+1 bug would show up as a real difference here."""
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    # Warm up before measuring: StoreSettings.load()'s get_or_create() and
    # the DB-backed cache/session both cost extra one-time queries on their
    # first-ever access, which would otherwise look like an N+1 difference
    # between the two measurements below even though it has nothing to do
    # with product count.
    client.get(LIST_URL)

    for _ in range(5):
        ProductFactory()
    with CaptureQueriesContext(connection) as captured_at_5:
        response = client.get(LIST_URL)
    assert response.status_code == 200
    queries_at_5 = len(captured_at_5)

    for _ in range(45):
        ProductFactory()
    assert Product.objects.count() == 50
    with CaptureQueriesContext(connection) as captured_at_50:
        response = client.get(LIST_URL)
    assert response.status_code == 200
    queries_at_50 = len(captured_at_50)

    assert queries_at_50 == queries_at_5, (
        f"query count grew with fixture count: {queries_at_5} at 5 products, "
        f"{queries_at_50} at 50 — likely an N+1"
    )
