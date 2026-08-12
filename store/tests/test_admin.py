from __future__ import annotations

import pytest
from django.contrib.admin.sites import AdminSite

from store.admin import StoreSettingsAdmin
from store.models import StoreSettings


@pytest.fixture
def admin_instance() -> StoreSettingsAdmin:
    return StoreSettingsAdmin(StoreSettings, AdminSite())


def test_add_permission_is_always_false(admin_instance, rf) -> None:
    request = rf.get("/django-admin/store/storesettings/")
    assert admin_instance.has_add_permission(request) is False


def test_delete_permission_is_always_false(admin_instance, rf) -> None:
    request = rf.get("/django-admin/store/storesettings/")
    assert admin_instance.has_delete_permission(request) is False


def test_delete_permission_is_false_even_with_an_object_given(admin_instance, rf) -> None:
    request = rf.get("/django-admin/store/storesettings/1/")
    assert admin_instance.has_delete_permission(request, StoreSettings(pk=1)) is False


@pytest.mark.django_db
def test_admin_changelist_shows_the_singleton_row(client, django_user_model) -> None:
    django_user_model.objects.create_superuser("root", "root@example.com", "pw-not-real-123")
    client.login(username="root", password="pw-not-real-123")
    StoreSettings.load()

    response = client.get("/django-admin/store/storesettings/")

    assert response.status_code == 200
    assert b"My Store" in response.content
    # the object-tools "Add" button is only rendered when has_add_permission
    # is true; its href is the one unambiguous signal (the icon sprite sheet
    # that ships with every admin page references "addlink" regardless).
    assert b'href="/django-admin/store/storesettings/add/"' not in response.content


@pytest.mark.django_db
def test_add_view_is_forbidden_even_for_a_superuser(client, django_user_model) -> None:
    django_user_model.objects.create_superuser("root", "root@example.com", "pw-not-real-123")
    client.login(username="root", password="pw-not-real-123")

    response = client.get("/django-admin/store/storesettings/add/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_delete_view_is_forbidden_even_for_a_superuser(client, django_user_model) -> None:
    django_user_model.objects.create_superuser("root", "root@example.com", "pw-not-real-123")
    client.login(username="root", password="pw-not-real-123")
    StoreSettings.load()

    response = client.get("/django-admin/store/storesettings/1/delete/")

    assert response.status_code == 403
