"""Private tablet sync API: /api/kiosk/sync/…"""

from __future__ import annotations

import json
import logging

import pytest
from django.contrib import admin
from django.db import models
from django.test import Client

from catalog.models import Product
from core.models import RateLimitAttempt
from noor.catalog import ProductRow
from noor.config import BACKUP_KEEP_NEWEST, BACKUP_MAX_BYTES, SYNC_RATE_LIMIT_POLICY
from noor.models import KioskBackup
from noor.tests.support import (
    BACKUP_URL,
    KIOSK_CATALOG_URL,
    LATEST_URL,
    PING_URL,
    PRIVATE_GET_URLS,
    TOKEN,
    auth,
    backup_body,
    published,
)
from noor.views import kiosk_item

VALID_BACKUP = {"format": "scent-style-backup", "version": 1, "items": [{"slug": "a", "qty": 2}]}


@pytest.fixture
def sync_token(settings) -> str:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = TOKEN
    return TOKEN


def _post_backup(client, body, **extra):  # type: ignore[no-untyped-def]
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    return client.post(
        BACKUP_URL,
        data=payload,
        content_type="application/json",
        secure=True,
        **{**auth(), **extra},
    )


# --- authentication ---------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
@pytest.mark.parametrize("url", PRIVATE_GET_URLS)
def test_missing_token_is_401(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.get(url, secure=True)

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorised"}


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
@pytest.mark.parametrize("url", PRIVATE_GET_URLS)
def test_wrong_token_is_401(client, url) -> None:  # type: ignore[no-untyped-def]
    response = client.get(url, secure=True, **auth("not-the-token-" + "y" * 32))

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorised"}


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_backup_upload_without_token_is_401_and_stores_nothing(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        BACKUP_URL, data=json.dumps(VALID_BACKUP), content_type="application/json", secure=True
    )

    assert response.status_code == 401
    assert KioskBackup.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
@pytest.mark.parametrize(
    "header",
    [TOKEN, f"Basic {TOKEN}", "Bearer", "Bearer ", f"Bearer {TOKEN[:-1]}", f"Bearer {TOKEN}x"],
)
def test_malformed_or_near_miss_authorization_is_401(client, header) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, secure=True, HTTP_AUTHORIZATION=header)

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_401_asks_for_a_bearer_token(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get(PING_URL, secure=True)["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
def test_right_token_is_200(client, sync_token) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, secure=True, **auth(sync_token))

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.django_db
def test_unconfigured_token_fails_closed(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = ""

    assert client.get(PING_URL, secure=True, HTTP_AUTHORIZATION="Bearer ").status_code == 401
    assert client.get(PING_URL, secure=True, **auth("")).status_code == 401


@pytest.mark.django_db
def test_too_short_configured_token_fails_closed(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = "short"

    assert client.get(PING_URL, secure=True, **auth("short")).status_code == 401


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_token_is_never_logged(client, caplog) -> None:  # type: ignore[no-untyped-def]
    wrong = "wrong-token-" + "z" * 32
    with caplog.at_level(logging.DEBUG):
        client.get(PING_URL, secure=True, **auth(wrong))
        client.get(PING_URL, secure=True, **auth(TOKEN))

    assert wrong not in caplog.text
    assert TOKEN not in caplog.text


# --- transport / CSRF / caching --------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_plain_http_is_refused_outside_debug(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, **auth())

    assert response.status_code == 403
    assert response.json() == {"error": "https_required"}


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_plain_http_is_allowed_in_local_debug(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.DEBUG = True

    assert client.get(PING_URL, **auth()).status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_post_is_csrf_exempt(sync_token) -> None:  # type: ignore[no-untyped-def]
    strict = Client(enforce_csrf_checks=True)

    assert _post_backup(strict, VALID_BACKUP).status_code == 201


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_private_responses_are_not_cacheable(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(PING_URL, secure=True, **auth())

    assert response["Cache-Control"] == "private, no-store"


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_preflight_needs_no_token_and_spends_no_rate_limit(client) -> None:  # type: ignore[no-untyped-def]
    response = client.options(
        BACKUP_URL,
        secure=True,
        HTTP_ORIGIN="https://noor.scentandstyle.pk",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
    )

    assert response.status_code == 204
    assert response["Access-Control-Allow-Origin"] == "https://noor.scentandstyle.pk"
    assert "Authorization" in response["Access-Control-Allow-Headers"]
    assert "POST" in response["Access-Control-Allow-Methods"]
    assert RateLimitAttempt.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_wrong_method_is_405_after_auth(client) -> None:  # type: ignore[no-untyped-def]
    assert client.post(PING_URL, secure=True, **auth()).status_code == 405
    assert client.get(BACKUP_URL, secure=True, **auth()).status_code == 405


# --- rate limit -------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_over_30_requests_a_minute_from_one_ip_is_429(client) -> None:  # type: ignore[no-untyped-def]
    ip = {"REMOTE_ADDR": "203.0.113.7"}
    for _ in range(SYNC_RATE_LIMIT_POLICY.max_attempts):
        assert client.get(PING_URL, secure=True, **auth(), **ip).status_code == 200

    blocked = client.get(PING_URL, secure=True, **auth(), **ip)

    assert blocked.status_code == 429
    assert blocked.json() == {"error": "rate_limited"}
    assert blocked["Retry-After"] == "60"
    # Another device is unaffected.
    other = client.get(PING_URL, secure=True, **auth(), REMOTE_ADDR="203.0.113.8")
    assert other.status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_failed_guesses_count_towards_the_limit(client) -> None:  # type: ignore[no-untyped-def]
    ip = {"REMOTE_ADDR": "203.0.113.9"}
    for _ in range(SYNC_RATE_LIMIT_POLICY.max_attempts):
        assert (
            client.get(PING_URL, secure=True, **auth("guess-" + "g" * 40), **ip).status_code == 401
        )

    # Even the right token is throttled once the guesser has used the budget.
    assert client.get(PING_URL, secure=True, **auth(), **ip).status_code == 429


# --- GET catalog/ -----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_kiosk_catalog_sends_counted_units(client) -> None:  # type: ignore[no-untyped-def]
    live = published("Khamrah", price="8500.00", stock=4)
    sold_out = published("Sold Out", price="1200.00", stock=0)
    published("Hidden Draft", status=Product.Status.DRAFT)

    response = client.get(KIOSK_CATALOG_URL, secure=True, **auth())

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"generatedAt", "items"}
    by_slug = {item["slug"]: item for item in payload["items"]}
    assert by_slug == {
        live.slug: {"slug": live.slug, "price": 8500, "stockQty": 4},
        sold_out.slug: {"slug": sold_out.slug, "price": 1200, "stockQty": 0},
    }
    quantities = [item["stockQty"] for item in by_slug.values()]
    assert all(isinstance(qty, int) and qty >= 0 for qty in quantities)


def _row(*, stock_qty: int | None, in_stock: bool) -> ProductRow:
    return ProductRow(
        slug="khamrah", name="Khamrah", brand="", category="Perfumes", price=8500,
        in_stock=in_stock, stock_qty=stock_qty, description="", image="",
        url="https://scentandstyle.pk/product/khamrah/",
        top_notes=(), heart_notes=(), base_notes=(),
    )  # fmt: skip


def test_known_count_is_sent_as_stock_qty() -> None:
    assert kiosk_item(_row(stock_qty=3, in_stock=True)) == {
        "slug": "khamrah", "price": 8500, "stockQty": 3,
    }  # fmt: skip


def test_unknown_count_sends_in_stock_without_a_number() -> None:
    sold_out = kiosk_item(_row(stock_qty=None, in_stock=False))
    available = kiosk_item(_row(stock_qty=None, in_stock=True))

    assert sold_out == {"slug": "khamrah", "price": 8500, "inStock": False}
    assert available == {"slug": "khamrah", "price": 8500, "inStock": True}
    assert "stockQty" not in sold_out
    assert "stockQty" not in available


# --- POST backup/ + GET backup/latest/ -------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_valid_backup_is_stored_and_201(client) -> None:  # type: ignore[no-untyped-def]
    response = _post_backup(client, VALID_BACKUP)

    assert response.status_code == 201
    stored = KioskBackup.objects.get()
    assert response.json() == {"storedAt": stored.received_at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert json.loads(stored.body) == VALID_BACKUP
    assert stored.size == len(json.dumps(VALID_BACKUP).encode())


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"this is not json", "invalid_json"),
        (b"", "invalid_json"),
        (b"\xff\xfe\x00", "invalid_json"),
        pytest.param(b"[" * 200_000, "invalid_json", id="deeply-nested-array"),
        (b'["scent-style-backup"]', "invalid_format"),
        (b'{"version": 1}', "invalid_format"),
        (b'{"format": "something-else"}', "invalid_format"),
    ],
)
def test_bad_backups_are_400_and_not_stored(client, body, code) -> None:  # type: ignore[no-untyped-def]
    response = _post_backup(client, body)

    assert response.status_code == 400
    assert response.json() == {"error": code}
    assert KioskBackup.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_backup_exactly_at_the_cap_is_accepted(client) -> None:  # type: ignore[no-untyped-def]
    # 5 MiB sails past Django's 2.5 MB request.body limit — proves the
    # stream is read directly rather than tripping DATA_UPLOAD_MAX_MEMORY_SIZE.
    response = _post_backup(client, backup_body(BACKUP_MAX_BYTES))

    assert response.status_code == 201
    assert KioskBackup.objects.get().size == BACKUP_MAX_BYTES


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_backup_one_byte_over_the_cap_is_413(client) -> None:  # type: ignore[no-untyped-def]
    response = _post_backup(client, backup_body(BACKUP_MAX_BYTES + 1))

    assert response.status_code == 413
    assert response.json() == {"error": "payload_too_large"}
    assert KioskBackup.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_backup_with_an_escaped_nul_round_trips(client) -> None:  # type: ignore[no-untyped-def]
    # Valid JSON that Postgres jsonb would reject — hence a TextField.
    raw = b'{"format": "scent-style-backup", "note": "a\\u0000b"}'

    assert _post_backup(client, raw).status_code == 201
    assert client.get(LATEST_URL, secure=True, **auth()).content == raw


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_only_the_newest_ten_backups_are_kept(client) -> None:  # type: ignore[no-untyped-def]
    for sequence in range(BACKUP_KEEP_NEWEST + 3):
        body = {"format": "scent-style-backup", "sequence": sequence}
        assert _post_backup(client, body).status_code == 201

    kept = [json.loads(row.body)["sequence"] for row in KioskBackup.objects.all()]
    assert len(kept) == BACKUP_KEEP_NEWEST
    assert kept == list(range(BACKUP_KEEP_NEWEST + 2, 2, -1))  # newest first; 0-2 pruned
    latest = client.get(LATEST_URL, secure=True, **auth()).json()
    assert latest["sequence"] == BACKUP_KEEP_NEWEST + 2


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_latest_is_404_when_nothing_was_uploaded(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(LATEST_URL, secure=True, **auth())

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


@pytest.mark.django_db
@pytest.mark.usefixtures("sync_token")
def test_latest_returns_the_newest_body_verbatim_as_utf8_json(client) -> None:  # type: ignore[no-untyped-def]
    _post_backup(client, {"format": "scent-style-backup", "n": 1})
    raw = '{"format":  "scent-style-backup", "shop": "Scent & Style", "name": "خمرہ"}'.encode()
    _post_backup(client, raw)

    response = client.get(LATEST_URL, secure=True, **auth())

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json; charset=utf-8"
    assert response.content == raw  # not re-serialised: spacing and key order intact


# --- backups are never publicly reachable ----------------------------------


def test_backups_are_not_in_the_admin_and_have_no_file_field() -> None:
    assert KioskBackup not in admin.site._registry
    file_fields = [f for f in KioskBackup._meta.get_fields() if isinstance(f, models.FileField)]
    assert file_fields == []
