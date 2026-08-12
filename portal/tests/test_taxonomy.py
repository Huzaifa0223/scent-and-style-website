from __future__ import annotations

import pytest

from catalog.factories import AttributeDefinitionFactory, BrandFactory, CategoryFactory
from catalog.models import AttributeDefinition, Brand, Category


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


@pytest.mark.django_db
def test_category_list_requires_login(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/admin-portal/categories/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_category_create_happy_path(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    response = client.post(
        "/admin-portal/categories/create/",
        {"name": "Fragrances", "position": 0, "meta_title": "", "meta_description": ""},
    )
    assert response.status_code == 302
    assert Category.objects.filter(name="Fragrances").exists()


@pytest.mark.django_db
def test_category_create_rejects_a_third_level(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """CategoryForm restricts the ``parent`` dropdown to top-level
    categories, but Category.clean() is the real enforcement — this proves
    the form surfaces that as a field error, not a 500."""
    _login_owner(client, django_user_model)
    top = CategoryFactory()
    sub = CategoryFactory(parent=top)

    response = client.post(
        "/admin-portal/categories/create/",
        {
            "name": "Too Deep",
            "parent": sub.pk,
            "position": 0,
            "meta_title": "",
            "meta_description": "",
        },
    )

    assert response.status_code == 200
    assert not Category.objects.filter(name="Too Deep").exists()


@pytest.mark.django_db
def test_category_edit_happy_path(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    category = CategoryFactory(name="Old Name")
    response = client.post(
        f"/admin-portal/categories/{category.pk}/edit/",
        {"name": "New Name", "position": 0, "meta_title": "", "meta_description": ""},
    )
    assert response.status_code == 302
    category.refresh_from_db()
    assert category.name == "New Name"


@pytest.mark.django_db
def test_brand_create_happy_path(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    response = client.post("/admin-portal/brands/create/", {"name": "Afnan"})
    assert response.status_code == 302
    assert Brand.objects.filter(name="Afnan").exists()


@pytest.mark.django_db
def test_brand_edit_happy_path(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    brand = BrandFactory(name="Old Brand")
    response = client.post(f"/admin-portal/brands/{brand.pk}/edit/", {"name": "New Brand"})
    assert response.status_code == 302
    brand.refresh_from_db()
    assert brand.name == "New Brand"


@pytest.mark.django_db
def test_attribute_definition_create_happy_path(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    response = client.post(
        "/admin-portal/attributes/create/",
        {"name": "Size", "is_filterable": "on", "is_variant_option": "on", "position": 0},
    )
    assert response.status_code == 302
    assert AttributeDefinition.objects.filter(name="Size").exists()


@pytest.mark.django_db
def test_attribute_value_add_and_remove(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    definition = AttributeDefinitionFactory(name="Size")

    response = client.post(
        f"/admin-portal/attributes/{definition.pk}/values/add/",
        {"value": "50ml", "position": 0},
    )
    assert response.status_code == 302
    value = definition.values.get(value="50ml")

    response = client.post(f"/admin-portal/attributes/{definition.pk}/values/{value.pk}/delete/")
    assert response.status_code == 302
    assert not definition.values.filter(pk=value.pk).exists()


@pytest.mark.django_db
def test_attribute_edit_page_lists_its_values(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    definition = AttributeDefinitionFactory(name="Color")
    definition.values.create(value="Red", slug="red")

    response = client.get(f"/admin-portal/attributes/{definition.pk}/edit/")

    assert response.status_code == 200
    assert b"Red" in response.content
