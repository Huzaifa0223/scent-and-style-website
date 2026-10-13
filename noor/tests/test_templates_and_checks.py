"""'Ask ScentIQ' on the storefront, and the deploy check for the sync token."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.template import Context, Template

from noor.checks import sync_token_is_configured
from noor.config import SYNC_TOKEN_MIN_LENGTH
from noor.tests.support import published
from store.models import DeliveryStrategy, StoreSettings

ASK_URL = "https://scentiq.scentandstyle.pk/#/ask"


@pytest.fixture(autouse=True)
def links_on(settings) -> None:  # type: ignore[no-untyped-def]
    """Everything in this module is about the buttons *when shown*, so the
    flag is on throughout; test_public_links_flag.py covers off/default."""
    settings.NOOR_PUBLIC_LINKS = True


def _html(response) -> str:  # type: ignore[no-untyped-def]
    return response.content.decode()


def _fab_tag(html: str) -> str:
    start = html.index("data-noor-fab")
    return html[html.rindex("<a", 0, start) : html.index("</a>", start)]


# --- floating button --------------------------------------------------------


@pytest.mark.django_db
def test_home_page_has_the_floating_button(client) -> None:  # type: ignore[no-untyped-def]
    html = _html(client.get("/"))

    tag = _fab_tag(html)
    assert f'href="{ASK_URL}"' in tag
    assert 'target="_blank"' in tag
    assert 'rel="noopener"' in tag
    assert "Ask ScentIQ" in tag


@pytest.mark.django_db
def test_button_is_on_listing_and_product_pages_too(client) -> None:  # type: ignore[no-untyped-def]
    product = published()

    assert "data-noor-fab" in _html(client.get("/products/"))
    assert "data-noor-fab" in _html(client.get(f"/product/{product.slug}/"))


@pytest.mark.django_db
def test_button_sits_above_the_whatsapp_button_when_there_is_one(client) -> None:  # type: ignore[no-untyped-def]
    store = StoreSettings.load()
    store.whatsapp_number = "03001234567"
    store.save()

    with_whatsapp = _fab_tag(_html(client.get("/")))

    assert "bottom: 6rem" in with_whatsapp


@pytest.mark.django_db
def test_button_drops_to_the_corner_without_a_whatsapp_button(client) -> None:  # type: ignore[no-untyped-def]
    store = StoreSettings.load()
    store.whatsapp_number = ""
    store.save()

    assert "bottom: 1.25rem" in _fab_tag(_html(client.get("/")))


@pytest.mark.django_db
def test_button_is_hidden_on_checkout(client) -> None:  # type: ignore[no-untyped-def]
    variant = published(stock=5).variants.get()
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})

    response = client.get("/checkout/")

    assert response.status_code == 200
    assert "data-noor-fab" not in _html(response)
    assert "#/ask" not in _html(response)


@pytest.mark.django_db
def test_button_is_hidden_on_order_confirmation(client) -> None:  # type: ignore[no-untyped-def]
    store = StoreSettings.load()
    store.delivery_strategy = DeliveryStrategy.FLAT_RATE
    store.flat_delivery_rate = Decimal("0.00")
    store.save()
    variant = published(stock=5).variants.get()
    client.post("/cart/add/", {"variant_id": variant.pk, "quantity": 1})
    checkout = client.post(
        "/checkout/",
        {
            "name": "Ayesha Khan",
            "mobile_number": "03001234567",
            "same_as_mobile": "on",
            "address": "House 1, Street 2",
            "city": "Karachi",
        },
    )
    assert checkout.status_code == 302

    response = client.get(checkout.url)

    assert response.status_code == 200
    assert "data-noor-fab" not in _html(response)


@pytest.mark.django_db
def test_button_is_absent_on_the_account_login_page(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/accounts/login/")

    assert response.status_code == 200
    assert "data-noor-fab" not in _html(response)
    assert "#/ask" not in _html(response)


# --- product page button ----------------------------------------------------


@pytest.mark.django_db
def test_product_page_links_to_find_similar_for_its_own_slug(client) -> None:  # type: ignore[no-untyped-def]
    product = published("Lattafa Khamrah")
    other = published("Another Perfume")

    html = _html(client.get(f"/product/{product.slug}/"))

    assert "Find similar with ScentIQ" in html
    assert f'href="https://scentiq.scentandstyle.pk/#/p/{product.slug}"' in html
    assert f"#/p/{other.slug}" not in html


@pytest.mark.django_db
def test_find_similar_opens_safely_in_a_new_tab_next_to_add_to_cart(client) -> None:  # type: ignore[no-untyped-def]
    product = published()

    html = _html(client.get(f"/product/{product.slug}/"))

    start = html.index("data-noor-similar")
    tag = html[html.rindex("<a", 0, start) : html.index("</a>", start)]
    assert 'target="_blank"' in tag
    assert 'rel="noopener"' in tag
    assert html.index("Add to cart") < start


# --- template tags ----------------------------------------------------------


def test_similar_url_quotes_the_slug() -> None:
    rendered = Template("{% load noor %}{% noor_similar_url slug %}").render(
        Context({"slug": "a b/c?d"})
    )

    assert rendered == "https://scentiq.scentandstyle.pk/#/p/a%20b%2Fc%3Fd"


def test_origin_comes_from_settings(settings) -> None:  # type: ignore[no-untyped-def]
    settings.NOOR_ORIGIN = "https://staging-noor.example"

    assert Template("{% load noor %}{% noor_ask_url %}").render(Context()) == (
        "https://staging-noor.example/#/ask"
    )


# --- deploy check -----------------------------------------------------------


def test_check_warns_when_the_token_is_unset(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = ""

    (message,) = sync_token_is_configured(None)

    assert message.id == "noor.W001"
    assert message.level < 40  # a warning, never an error: the shop must still boot


def test_check_warns_when_the_token_is_too_short(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = "x" * (SYNC_TOKEN_MIN_LENGTH - 1)

    assert [m.id for m in sync_token_is_configured(None)] == ["noor.W001"]


def test_check_is_silent_with_a_long_enough_token(settings) -> None:  # type: ignore[no-untyped-def]
    settings.SCENT_SYNC_TOKEN = "x" * SYNC_TOKEN_MIN_LENGTH

    assert sync_token_is_configured(None) == []
