"""Roadmap Stage 3 acceptance gate 4, and the correction that made it mean
something: a staff user with zero permissions is blocked from literally
everything, including the portal's own product list, which would prove
nothing about permission discrimination. The seeded "Staff" group
(accounts/migrations/0001_create_staff_group.py) grants view/add/change on
catalog only — these tests show a staff member *can* use the catalog
surfaces and *cannot* reach store settings or user management.

"Store settings and user management" is /django-admin/, not a portal page —
the portal doesn't have one yet (Stage 1 log's open question; Stage 17
builds the portal-native replacement). Confirmed empirically before writing
these: a user with is_staff=False gets redirected (302) rather than denied
by django-admin's own login gate, which wouldn't satisfy gate 4's "403, not
a hidden link" — so the fixture here needs is_staff=True (can log into
django-admin at all) with no model permissions on store.StoreSettings or
auth.User, which is exactly what a real deploy would look like for a
trusted employee who's never been granted those permissions.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group

from catalog.factories import ProductFactory


def _staff_user(django_user_model):  # type: ignore[no-untyped-def]
    """is_staff=True only for django-admin login capability, per the module
    docstring — the portal's own access control never looks at is_staff,
    only at the Staff group's catalog permissions."""
    user = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    user.groups.add(Group.objects.get(name="Staff"))
    return user


@pytest.mark.django_db
def test_staff_group_was_seeded_with_catalog_permissions_only() -> None:
    group = Group.objects.get(name="Staff")
    codenames = set(group.permissions.values_list("codename", flat=True))
    assert "view_product" in codenames
    assert "add_product" in codenames
    assert "change_product" in codenames
    assert not any(codename.startswith("delete_") for codename in codenames)
    assert group.permissions.filter(content_type__app_label="store").count() == 0
    assert group.permissions.filter(content_type__app_label="auth").count() == 0


@pytest.mark.django_db
def test_staff_can_load_the_product_list(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = _staff_user(django_user_model)
    client.force_login(staff)
    ProductFactory(name="Visible To Staff")

    response = client.get("/admin-portal/products/")

    assert response.status_code == 200
    assert b"Visible To Staff" in response.content


@pytest.mark.django_db
def test_staff_can_create_a_category(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = _staff_user(django_user_model)
    client.force_login(staff)

    response = client.post(
        "/admin-portal/categories/create/",
        {"name": "Staff Made This", "position": 0, "meta_title": "", "meta_description": ""},
    )

    assert response.status_code == 302


@pytest.mark.django_db
def test_staff_cannot_load_store_settings_in_admin(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = _staff_user(django_user_model)
    client.force_login(staff)

    response = client.get("/django-admin/store/storesettings/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_cannot_load_user_management_in_admin(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = _staff_user(django_user_model)
    client.force_login(staff)

    response = client.get("/django-admin/auth/user/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_load_store_settings_and_user_management_in_admin(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)

    assert client.get("/django-admin/store/storesettings/").status_code == 200
    assert client.get("/django-admin/auth/user/").status_code == 200
