"""NOOR_PUBLIC_LINKS: the website buttons stay hidden until Noor's site is live.

The flag gates only the two storefront buttons — never the API endpoints.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.template import Context, Template

from noor.tests.support import (
    CATALOG_URL,
    KIOSK_CATALOG_URL,
    PING_URL,
    PRODUCTS_URL,
    TOKEN,
    auth,
    published,
)
from store.models import DeliveryStrategy, StoreSettings

NOOR_MARKERS = (
    "data-noor-fab",
    "data-noor-similar",
    "Ask Noor",
    "Find similar with Noor",
    "#/noor",
)


def _assert_no_noor_links(response) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 200
    html = response.content.decode()
    for marker in NOOR_MARKERS:
        assert marker not in html
    assert "noor.scentandstyle.pk" not in html


def _storefront_pages(client):  # type: ignore[no-untyped-def]
    product = published("Lattafa Khamrah")
    for path in ("/", "/products/", f"/product/{product.slug}/", "/brands/"):
        yield client.get(path)


@pytest.mark.django_db
def test_setting_defaults_to_off(settings) -> None:  # type: ignore[no-untyped-def]
    # The real configuration, no override: nothing in .env turns it on here.
    assert settings.NOOR_PUBLIC_LINKS is False


@pytest.mark.django_db
def test_buttons_are_absent_by_default_on_every_storefront_page(client) -> None:  # type: ignore[no-untyped-def]
    for response in _storefront_pages(client):
        _assert_no_noor_links(response)


@pytest.mark.django_db
def test_buttons_are_absent_when_explicitly_off(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.NOOR_PUBLIC_LINKS = False

    for response in _storefront_pages(client):
        _assert_no_noor_links(response)


@pytest.mark.django_db
def test_buttons_appear_when_on_base_page_and_product_page(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.NOOR_PUBLIC_LINKS = True
    product = published("Lattafa Khamrah")

    home = client.get("/").content.decode()
    pdp = client.get(f"/product/{product.slug}/").content.decode()

    assert "data-noor-fab" in home
    assert "https://noor.scentandstyle.pk/#/noor" in home
    assert "data-noor-fab" in pdp
    assert "data-noor-similar" in pdp
    assert f"https://noor.scentandstyle.pk/#/p/{product.slug}" in pdp


@pytest.mark.django_db
@pytest.mark.parametrize("raw", ["true", "True", "1", "yes", "on"])
def test_env_value_true_enables_the_flag(monkeypatch, raw) -> None:  # type: ignore[no-untyped-def]
    # Same parser settings/base.py uses (django-environ's Env.bool).
    from config.settings.base import env

    monkeypatch.setenv("NOOR_PUBLIC_LINKS", raw)

    assert env.bool("NOOR_PUBLIC_LINKS", default=False) is True


@pytest.mark.django_db
@pytest.mark.parametrize("raw", ["false", "False", "0", "no", "off", ""])
def test_env_value_false_or_blank_keeps_the_flag_off(monkeypatch, raw) -> None:  # type: ignore[no-untyped-def]
    from config.settings.base import env

    monkeypatch.setenv("NOOR_PUBLIC_LINKS", raw)

    assert env.bool("NOOR_PUBLIC_LINKS", default=False) is False


@pytest.mark.django_db
def test_checkout_and_confirmation_never_show_them_even_when_on(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.NOOR_PUBLIC_LINKS = True
    store = StoreSettings.load()
    store.delivery_strategy = DeliveryStrategy.FLAT_RATE
    store.flat_delivery_rate = Decimal("0.00")
    store.save()
    variant = published(stock=5).variants.get()
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    checkout_page = client.get("/checkout/")
    placed = client.post(
        "/checkout/",
        {
            "name": "Ayesha Khan",
            "mobile_number": "03001234567",
            "same_as_mobile": "on",
            "address": "House 1, Street 2",
            "city": "Karachi",
        },
    )
    confirmation = client.get(placed.url)

    assert placed.status_code == 302
    for response in (checkout_page, confirmation):
        assert response.status_code == 200
        html = response.content.decode()
        assert "data-noor-fab" not in html
        assert "Ask Noor" not in html


@pytest.mark.django_db
def test_apis_are_unaffected_by_the_flag(client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = TOKEN
    published("Khamrah", stock=3)

    for flag in (False, True):
        settings.NOOR_PUBLIC_LINKS = flag
        assert client.get(CATALOG_URL).status_code == 200
        assert client.get(PRODUCTS_URL).status_code == 200
        assert client.get(PING_URL, secure=True, **auth()).json() == {"ok": True}
        kiosk = client.get(KIOSK_CATALOG_URL, secure=True, **auth())
        assert kiosk.status_code == 200
        assert kiosk.json()["items"][0]["stockQty"] == 3


def test_template_tag_reports_the_flag(settings) -> None:  # type: ignore[no-untyped-def]
    template = Template("{% load noor %}{% noor_links_enabled as on %}{{ on }}")

    settings.NOOR_PUBLIC_LINKS = False
    assert template.render(Context()) == "False"
    settings.NOOR_PUBLIC_LINKS = True
    assert template.render(Context()) == "True"
