"""Unit-level tests of PortalPermissionRequiredMixin's own decision logic —
called directly via RequestFactory, bypassing URL routing and Django's
exception-to-response middleware, so a denied request surfaces as a raised
exception rather than an HTTP response. That's deliberate: this file proves
the *mechanism* (who gets let in, who gets a redirect, who gets denied).
The full request/response 403 conversion is proven separately by
portal/tests/test_permissions.py's real Client-based gate-4 test.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.views import View

from accounts.mixins import PortalPermissionRequiredMixin


class _DummyView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.view_product",)

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("ok")


@pytest.mark.django_db
def test_anonymous_user_redirected_to_login(rf) -> None:  # type: ignore[no-untyped-def]
    request = rf.get("/whatever/")
    request.user = AnonymousUser()

    response = _DummyView.as_view()(request)

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_authenticated_user_without_permission_is_denied(rf, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(username="nobody", password="x")
    request = rf.get("/whatever/")
    request.user = user

    with pytest.raises(PermissionDenied):
        _DummyView.as_view()(request)


@pytest.mark.django_db
def test_superuser_bypasses_permission_check(rf, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_superuser(
        username="owner", email="owner@example.com", password="x"
    )
    request = rf.get("/whatever/")
    request.user = user

    response = _DummyView.as_view()(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_user_with_the_exact_permission_string_is_allowed(rf, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Proves the permission string actually resolves and is checked — a
    typo like "catalog.view_prodcut" would otherwise pass silently on any
    test that only ever exercises a superuser."""
    user = django_user_model.objects.create_user(username="staffer", password="x")
    permission = Permission.objects.get(codename="view_product", content_type__app_label="catalog")
    user.user_permissions.add(permission)
    request = rf.get("/whatever/")
    request.user = user

    response = _DummyView.as_view()(request)

    assert response.status_code == 200


@pytest.mark.django_db
def test_user_with_an_unrelated_permission_is_still_denied(rf, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(username="staffer", password="x")
    permission = Permission.objects.get(codename="view_category", content_type__app_label="catalog")
    user.user_permissions.add(permission)
    request = rf.get("/whatever/")
    request.user = user

    with pytest.raises(PermissionDenied):
        _DummyView.as_view()(request)
