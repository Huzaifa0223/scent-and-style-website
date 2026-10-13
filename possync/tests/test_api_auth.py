"""/api/pos/sync/ — the same bearer pipeline as the kiosk API, with its own
secret and its own rate-limit bucket."""

from __future__ import annotations

import json
import logging

import pytest
from django.test import Client

from core.models import RateLimitAttempt
from noor.config import SYNC_RATE_LIMIT_POLICY
from possync.checks import pos_token_is_configured
from possync.tests.support import (
    PING_URL,
    POS_TOKEN,
    STOCK_URL,
    WEB_ORDERS_URL,
    ack_url,
    auth,
    snapshot,
)

OTHER_TOKEN = "tablet-sync-token-" + "t" * 32
ENDPOINTS = [
    pytest.param("get", PING_URL, id="ping"),
    pytest.param("post", STOCK_URL, id="stock"),
    pytest.param("get", WEB_ORDERS_URL, id="web-orders"),
    pytest.param("post", ack_url(1), id="ack"),
]


@pytest.fixture
def tokens(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = POS_TOKEN
    settings.SCENT_SYNC_TOKEN = OTHER_TOKEN


def _call(client, method: str, url: str, **extra):  # type: ignore[no-untyped-def]
    if method == "post":
        return client.post(url, data=json.dumps({}), content_type="application/json", **extra)
    return client.get(url, **extra)


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
@pytest.mark.parametrize(("method", "url"), ENDPOINTS)
def test_missing_or_wrong_token_is_401(client, method, url) -> None:  # type: ignore[no-untyped-def]
    for extra in ({}, auth("wrong-" + "w" * 40), {"HTTP_AUTHORIZATION": f"Basic {POS_TOKEN}"}):
        response = _call(client, method, url, secure=True, **extra)

        assert response.status_code == 401
        assert response.json() == {"error": "unauthorised"}
        assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
@pytest.mark.parametrize(("method", "url"), ENDPOINTS)
def test_the_tablet_token_does_not_open_the_pos_api(client, method, url) -> None:  # type: ignore[no-untyped-def]
    response = _call(client, method, url, secure=True, **auth(OTHER_TOKEN))

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_the_pos_token_does_not_open_the_tablet_api(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/kiosk/sync/ping/", secure=True, **auth(POS_TOKEN))

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_right_token_pings(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, secure=True, **auth())

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.django_db
@pytest.mark.parametrize("configured", ["", "short"])
def test_unset_or_short_token_fails_closed(client, settings, configured) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = configured

    assert client.get(PING_URL, secure=True, **auth(configured)).status_code == 401


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_pos_api_sends_no_cors_headers_and_is_not_cacheable(client) -> None:  # type: ignore[no-untyped-def]
    origin = {"HTTP_ORIGIN": "https://noor.scentandstyle.pk"}

    for response in (
        client.get(PING_URL, secure=True, **auth(), **origin),
        client.get(PING_URL, secure=True, **origin),  # 401
        client.options(STOCK_URL, secure=True, **auth(), **origin),  # 405, not a preflight
    ):
        assert [h for h in response.headers if h.lower().startswith("access-control-")] == []
        assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_plain_http_is_refused_outside_debug(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, **auth())

    assert response.status_code == 403
    assert response.json() == {"error": "https_required"}


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_post_is_csrf_exempt() -> None:
    strict = Client(enforce_csrf_checks=True)

    response = strict.post(
        STOCK_URL,
        data=json.dumps(snapshot([])),
        content_type="application/json",
        secure=True,
        **auth(),
    )

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_wrong_method_is_405_after_auth(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post(PING_URL, secure=True, **auth()).status_code == 405
    assert client.get(STOCK_URL, secure=True, **auth()).status_code == 405
    assert client.post(WEB_ORDERS_URL, secure=True, **auth()).status_code == 405


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_rate_limit_has_its_own_bucket(client) -> None:  # type: ignore[no-untyped-def]
    ip = {"REMOTE_ADDR": "203.0.113.50"}
    for _ in range(SYNC_RATE_LIMIT_POLICY.max_attempts):
        assert client.get(PING_URL, secure=True, **auth(), **ip).status_code == 200

    blocked = client.get(PING_URL, secure=True, **auth(), **ip)
    tablet = client.get("/api/kiosk/sync/ping/", secure=True, **auth(OTHER_TOKEN), **ip)

    assert blocked.status_code == 429
    assert blocked.json() == {"error": "rate_limited"}
    assert blocked["Retry-After"] == "60"
    assert tablet.status_code == 200  # same IP, other API: untouched
    assert RateLimitAttempt.objects.filter(scope="pos_sync").count() == 30


@pytest.mark.django_db
@pytest.mark.usefixtures("tokens")
def test_tokens_are_never_logged(client, caplog) -> None:  # type: ignore[no-untyped-def]
    wrong = "wrong-" + "z" * 40
    with caplog.at_level(logging.DEBUG):
        client.get(PING_URL, secure=True, **auth(wrong))
        client.get(PING_URL, secure=True, **auth())

    assert wrong not in caplog.text
    assert POS_TOKEN not in caplog.text


def test_check_warns_when_the_pos_token_is_missing(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = ""

    (message,) = pos_token_is_configured(None)

    assert message.id == "possync.W001"
    assert message.level < 40  # warning, never an error


def test_check_is_silent_with_a_long_enough_token(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_POS_TOKEN = POS_TOKEN

    assert pos_token_is_configured(None) == []
