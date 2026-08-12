from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_login_page_renders_for_anonymous_user(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert b"Log in" in response.content


@pytest.mark.django_db
def test_valid_credentials_log_in_and_redirect(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")
    response = client.post("/accounts/login/", {"username": "owner", "password": "correct-horse"})
    assert response.status_code == 302


@pytest.mark.django_db
def test_invalid_credentials_show_error_and_do_not_log_in(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")
    response = client.post("/accounts/login/", {"username": "owner", "password": "wrong"})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_already_authenticated_user_is_redirected_away_from_login(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(username="owner", password="x")
    client.force_login(user)
    response = client.get("/accounts/login/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_logout_requires_post(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(username="owner", password="x")
    client.force_login(user)
    response = client.get("/accounts/logout/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_logout_via_post_logs_out_and_redirects(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(username="owner", password="x")
    client.force_login(user)
    response = client.post("/accounts/logout/")
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session
