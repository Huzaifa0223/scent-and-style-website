from __future__ import annotations

import pytest

from core.models import RateLimitAttempt, RateLimitScope
from core.ratelimit import LOGIN_RATE_LIMIT_POLICY, record_attempt


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


@pytest.mark.django_db
def test_gate3_repeated_login_attempts_are_rate_limited(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")
    for _ in range(LOGIN_RATE_LIMIT_POLICY.max_attempts):
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="127.0.0.1", succeeded=True)

    response = client.post("/accounts/login/", {"username": "owner", "password": "correct-horse"})

    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_repeated_failed_logins_lock_out_further_attempts(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")
    for _ in range(LOGIN_RATE_LIMIT_POLICY.lockout_failure_threshold):  # type: ignore[arg-type]
        record_attempt(scope=RateLimitScope.LOGIN, ip_address="127.0.0.1", succeeded=False)

    response = client.post("/accounts/login/", {"username": "owner", "password": "correct-horse"})

    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_a_failed_login_is_recorded_as_a_failed_ratelimit_attempt(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")

    client.post("/accounts/login/", {"username": "owner", "password": "wrong"})

    attempt = RateLimitAttempt.objects.get(scope=RateLimitScope.LOGIN)
    assert attempt.succeeded is False


@pytest.mark.django_db
def test_a_successful_login_is_recorded_as_a_succeeded_ratelimit_attempt(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    django_user_model.objects.create_user(username="owner", password="correct-horse")

    client.post("/accounts/login/", {"username": "owner", "password": "correct-horse"})

    attempt = RateLimitAttempt.objects.get(scope=RateLimitScope.LOGIN)
    assert attempt.succeeded is True
