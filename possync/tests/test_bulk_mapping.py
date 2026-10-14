"""POS mapping page: size warnings, doubled brands, "review and confirm all
0.90 matches", and bulk "not sold online". Nothing here may link a product
without an explicit tick."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group

from catalog.models import ProductVariant
from possync import services
from possync.models import PosMappingEvent, PosProduct
from possync.tests.support import mapped_variant

MAPPING = "/admin-portal/pos/"
BULK = MAPPING + "bulk-review/"
BULK_NOT_ONLINE = MAPPING + "bulk-not-online/"


@pytest.fixture
def owner(client, django_user_model):  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_superuser("owner", "o@example.com", "pw-not-used")
    client.force_login(user)
    return user


def _pos(sku: str, name: str, *, brand: str = "Armaf", **fields: object) -> PosProduct:
    return PosProduct.objects.create(sku=sku, brand=brand, name=name, **fields)


# --- size warning ------------------------------------------------------------


@pytest.mark.django_db
def test_row_shows_a_visible_warning_when_the_sizes_differ(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Club De Nuit Intense 50ml", brand="Armaf")
    _pos("CDN-100", "Club De Nuit Intense 100ml")

    html = client.get(MAPPING).content.decode()

    assert "data-size-warning" in html
    assert "Size differs: POS says 100ml, website says 50ml" in html


@pytest.mark.django_db
def test_no_size_warning_when_the_sizes_agree(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Club De Nuit Intense 100ml", brand="Armaf")
    _pos("CDN-100", "Club De Nuit Intense 100ml")

    html = client.get(MAPPING).content.decode()

    assert "data-size-warning" not in html
    assert "Club De Nuit Intense" in html


# --- gift sets / doubled brand on the page -----------------------------------


@pytest.mark.django_db
def test_page_never_offers_a_gift_set_for_a_plain_bottle(client, owner) -> None:  # type: ignore[no-untyped-def]
    gift = mapped_variant(None, name="9pm Gift Set", brand="Afnan")
    _pos("AFN-9PM", "9pm 100ml", brand="Afnan")

    html = client.get(MAPPING).content.decode()

    assert f'name="variant_id" value="{gift.pk}"' not in html
    assert "No close match found" in html


@pytest.mark.django_db
def test_page_shows_the_brand_once_when_the_pos_name_repeats_it(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("AFN-HS", "Afnan Historic Sahara", brand="Afnan")

    html = client.get(MAPPING).content.decode()

    assert "Afnan Historic Sahara" in html
    assert "Afnan Afnan" not in html


# --- bulk review -------------------------------------------------------------


@pytest.mark.django_db
def test_page_links_to_the_bulk_review(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("A-1", "Anything")

    html = client.get(MAPPING).content.decode()

    assert "Review and confirm all 0.90 matches" in html
    assert BULK in html


@pytest.mark.django_db
def test_review_lists_confident_matches_with_both_prices_and_maps_nothing(  # type: ignore[no-untyped-def]
    client, owner
) -> None:
    variant = mapped_variant(
        None, name="Club De Nuit Intense 100ml", brand="Armaf", price="9500.00"
    )
    _pos("CDN", "Club De Nuit Intense 100ml", price=Decimal("9000.00"))

    response = client.get(BULK)
    html = response.content.decode()

    assert response.status_code == 200
    assert "Club De Nuit Intense" in html
    assert "Rs. 9000.00" in html and "Rs. 9500.00" in html  # POS price and website price
    assert f'value="{PosProduct.objects.get(sku="CDN").pk}:{variant.pk}"' in html
    variant.refresh_from_db()
    assert variant.pos_sku is None
    assert PosMappingEvent.objects.count() == 0


@pytest.mark.django_db
def test_review_leaves_out_weak_gift_set_and_size_mismatched_rows(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Khamrah 50ml", brand="Lattafa")
    mapped_variant(None, name="9pm Gift Set", brand="Afnan")
    mapped_variant(None, name="Oud Aswad", brand="Lattafa")
    _pos("K-100", "Khamrah 100ml", brand="Lattafa")  # size differs
    _pos("AFN-9", "9pm", brand="Afnan")  # plain bottle vs gift set
    _pos("L-OUD", "Oud Something Else", brand="Lattafa")  # weak

    html = client.get(BULK).content.decode()

    assert html.count("data-proposal") == 0
    assert "No unmapped POS product has a clear-cut match" in html


@pytest.mark.django_db
def test_review_includes_rows_whose_size_is_not_stated_and_says_so(client, owner) -> None:  # type: ignore[no-untyped-def]
    # Owner decision 2026-10-14: the website's variants almost never state a
    # size (2 of 163 on the live catalogue), so "size unknown" must not hide a
    # clear-cut match. The size is shown instead and nothing is pre-ticked.
    web_plain = mapped_variant(None, name="Khamrah", brand="Lattafa")
    pos_known = _pos("K-100", "Khamrah 100ml", brand="Lattafa")
    mapped_variant(None, name="Tres", brand="Armaf")
    _pos("TRES", "Tres")
    mapped_variant(None, name="Tres Sport 100ml", brand="Armaf")
    _pos("TRES-S", "Tres Sport")

    html = client.get(BULK).content.decode()

    assert html.count("data-proposal") >= 3
    assert f'value="{pos_known.pk}:{web_plain.pk}"' in html
    assert "POS: 100ml · website: not stated" in html
    assert "No size stated on either side" in html
    assert "POS: not stated · website: 100ml" in html
    assert "checked" not in html.split("<tbody", 1)[1]  # never pre-ticked
    assert "data-check-size" not in html  # 100 ml is the usual bottle


@pytest.mark.django_db
def test_review_flags_an_unusual_pos_size_for_a_second_look(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Zumar", brand="Ahmed Al Maghribi")
    _pos("ZUM-60", "Zumar 60ml", brand="Ahmed Al Maghribi")

    html = client.get(BULK).content.decode()

    assert "data-check-size" in html
    assert "Check size" in html
    assert "marked <strong>check size</strong>" in html


@pytest.mark.django_db
def test_review_still_leaves_out_a_known_size_mismatch(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Khamrah 50ml", brand="Lattafa")
    _pos("K-100", "Khamrah 100ml", brand="Lattafa")

    html = client.get(BULK).content.decode()

    # A known, different size drops the score below the threshold, so the row
    # is never proposed at all (it stays on the one-by-one page with a warning).
    assert html.count("data-proposal") == 0
    assert "No unmapped POS product has a clear-cut match" in html


# --- guided steps and the "hide watches" page --------------------------------

HIDE = MAPPING + "hide-non-perfume/"


@pytest.mark.django_db
def test_mapping_page_shows_the_steps_with_live_counts(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Khamrah", brand="Lattafa")
    _pos("K-100", "Khamrah 100ml", brand="Lattafa", category="Perfume")
    _pos("W-1", "Ladies Watch", brand="Casio", category="Watches")
    _pos("W-2", "Mens Watch", brand="Casio", category="Watches")

    html = client.get(MAPPING).content.decode()

    assert "data-mapping-guide" in html
    assert "Do it in this order" in html
    assert "Review 2 item(s)" in html  # step 2: the two watches
    assert "Review 1 match(es)" in html  # step 3: Khamrah
    assert HIDE in html and BULK in html


@pytest.mark.django_db
def test_steps_say_done_when_nothing_is_left(client, owner) -> None:  # type: ignore[no-untyped-def]
    html = client.get(MAPPING).content.decode()
    assert "Upload the POS product CSV with the form below." in html
    assert "Available after step 1." in html

    _pos("W-1", "Ladies Watch", brand="Casio", category="Watches", not_online=True)
    html = client.get(MAPPING).content.decode()

    assert "POS products are loaded" in html
    assert "Nothing left to hide." in html
    assert "No clear matches waiting." in html


@pytest.mark.django_db
def test_hide_page_lists_only_unlinked_watches_all_ticked_and_changes_nothing(  # type: ignore[no-untyped-def]
    client, owner
) -> None:
    watch = _pos("W-1", "Ladies Watch", brand="Casio", category="Watches")
    _pos("P-1", "Khamrah 100ml", brand="Lattafa", category="Perfume")
    _pos("W-OFF", "Old Watch", brand="Casio", category="Watches", not_online=True)

    response = client.get(HIDE)
    html = response.content.decode()

    assert response.status_code == 200
    assert html.count("data-hide-row") == 1
    assert "Ladies Watch" in html and "Khamrah" not in html and "Old Watch" not in html
    assert "checked" in html
    watch.refresh_from_db()
    assert watch.not_online is False


@pytest.mark.django_db
def test_hide_page_posts_to_the_bulk_action_and_returns_to_the_steps(client, owner) -> None:  # type: ignore[no-untyped-def]
    watch = _pos("W-1", "Ladies Watch", brand="Casio", category="Watches")
    html = client.get(HIDE).content.decode()
    assert BULK_NOT_ONLINE in html

    response = client.post(
        BULK_NOT_ONLINE, {"pos_ids": [str(watch.pk)], "next": MAPPING}, follow=True
    )

    watch.refresh_from_db()
    assert watch.not_online is True
    assert response.redirect_chain[-1][0] == MAPPING


@pytest.mark.django_db
def test_hide_page_needs_the_mapping_permission(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user(
        "staff", "s@example.com", "pw-not-used", is_staff=True
    )
    client.force_login(staff)

    assert client.get(HIDE).status_code in (302, 403)


@pytest.mark.django_db
def test_hint_explains_where_the_tick_boxes_went_on_other_lists(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("A-1", "Anything", category="Perfume")

    assert "data-bulk-hint" not in client.get(MAPPING).content.decode()
    assert "data-bulk-hint" in client.get(MAPPING + "?status=all").content.decode()


@pytest.mark.django_db
def test_review_skips_ties_and_a_variant_proposed_twice(client, owner) -> None:  # type: ignore[no-untyped-def]
    # Two identical website products: a tie for one POS row (which is right?).
    mapped_variant(None, name="Tres", brand="Armaf")
    mapped_variant(None, name="Tres", brand="Armaf")
    _pos("TRES", "Tres")
    # One variant, two POS rows: at most one can be right.
    mapped_variant(None, name="Khamrah", brand="Lattafa")
    _pos("K-A", "Khamrah", brand="Lattafa")
    _pos("K-B", "Khamrah", brand="Lattafa")

    html = client.get(BULK).content.decode()

    assert html.count("data-proposal") == 0
    assert "data-left-out" in html


@pytest.mark.django_db
def test_confirm_maps_only_the_ticked_rows(client, owner) -> None:  # type: ignore[no-untyped-def]
    first = mapped_variant(None, name="Club De Nuit Intense 100ml", brand="Armaf")
    second = mapped_variant(None, name="Khamrah 100ml", brand="Lattafa")
    pos_first = _pos("CDN", "Club De Nuit Intense 100ml")
    _pos("KHM", "Khamrah 100ml", brand="Lattafa")
    assert client.get(BULK).content.decode().count("data-proposal") == 2

    response = client.post(BULK, {"pair": [f"{pos_first.pk}:{first.pk}"]}, follow=True)

    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.pos_sku, second.pos_sku) == ("CDN", None)
    assert b"1 POS product(s) mapped" in response.content
    event = PosMappingEvent.objects.get(action=PosMappingEvent.Action.MAPPED)
    assert (event.pos_sku, event.actor) == ("CDN", owner)
    assert "Bulk confirmation" in event.note


@pytest.mark.django_db
def test_confirm_with_nothing_ticked_maps_nothing(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None, name="Khamrah", brand="Lattafa")
    _pos("KHM", "Khamrah", brand="Lattafa")

    response = client.post(BULK, {}, follow=True)

    variant.refresh_from_db()
    assert variant.pos_sku is None
    assert b"Nothing was ticked" in response.content


@pytest.mark.django_db
def test_a_stale_row_is_reported_and_the_rest_still_map(client, owner) -> None:  # type: ignore[no-untyped-def]
    taken = mapped_variant("OTHER", name="Khamrah", brand="Lattafa")
    free = mapped_variant(None, name="Tres", brand="Armaf")
    stale = _pos("KHM", "Khamrah", brand="Lattafa")
    good = _pos("TRES", "Tres")

    response = client.post(
        BULK, {"pair": [f"{stale.pk}:{taken.pk}", f"{good.pk}:{free.pk}"]}, follow=True
    )

    free.refresh_from_db()
    assert free.pos_sku == "TRES"
    assert b"already mapped to POS SKU OTHER" in response.content


@pytest.mark.django_db
def test_garbage_pair_values_are_ignored(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Khamrah", brand="Lattafa")

    response = client.post(BULK, {"pair": ["x:y", "12", ":", "1:"]}, follow=True)

    assert response.status_code == 200
    assert ProductVariant.objects.filter(pos_sku__isnull=False).count() == 0


@pytest.mark.django_db
def test_tick_all_link_pre_ticks_the_checkboxes_but_still_needs_confirm(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None, name="Khamrah 100ml", brand="Lattafa")
    _pos("KHM", "Khamrah 100ml", brand="Lattafa")

    plain = client.get(BULK).content.decode()
    ticked = client.get(BULK, {"tick": "all"}).content.decode()

    assert "checked" not in plain.split("<tbody")[1]
    assert "checked" in ticked.split("<tbody")[1]
    assert ProductVariant.objects.filter(pos_sku__isnull=False).count() == 0


# --- bulk "not sold online" ---------------------------------------------------


@pytest.mark.django_db
def test_bulk_not_online_marks_every_ticked_row_and_audits_each(client, owner) -> None:  # type: ignore[no-untyped-def]
    watch = _pos("W-1", "F-91W", brand="Casio", category="Watches")
    shades = _pos("S-1", "Aviator", brand="RayBan", category="Sunglasses")
    kept = _pos("P-1", "Khamrah", brand="Lattafa", category="Perfumes")

    response = client.post(
        BULK_NOT_ONLINE, {"pos_ids": [watch.pk, shades.pk], "next": MAPPING}, follow=True
    )

    watch.refresh_from_db()
    shades.refresh_from_db()
    kept.refresh_from_db()
    assert (watch.not_online, shades.not_online, kept.not_online) == (True, True, False)
    assert PosMappingEvent.objects.filter(action="marked_not_online").count() == 2
    assert b"2 POS product(s) marked not sold online" in response.content


@pytest.mark.django_db
def test_bulk_not_online_skips_a_mapped_product_and_says_so(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("M-1", name="Mapped")
    mapped = _pos("M-1", "Mapped")
    loose = _pos("L-1", "Loose")

    response = client.post(BULK_NOT_ONLINE, {"pos_ids": [mapped.pk, loose.pk]}, follow=True)

    mapped.refresh_from_db()
    loose.refresh_from_db()
    assert (mapped.not_online, loose.not_online) == (False, True)
    assert b"Remove the mapping first" in response.content


@pytest.mark.django_db
def test_bulk_not_online_with_nothing_ticked_changes_nothing(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("L-1", "Loose")

    response = client.post(BULK_NOT_ONLINE, {"pos_ids": ["abc"]}, follow=True)

    assert b"Tick at least one product" in response.content
    assert PosProduct.objects.filter(not_online=True).count() == 0


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("Watches", True),
        ("Mens Watch", True),
        ("SUNGLASSES", True),
        ("Accessories", True),
        ("Perfumes", False),
        ("Attar", False),
        ("", False),
    ],
)
def test_category_hint(category: str, expected: bool) -> None:
    assert services.looks_not_sold_online(category) is expected


@pytest.mark.django_db
def test_rows_in_a_watch_category_are_flagged_and_tickable_in_one_click(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("W-1", "F-91W", brand="Casio", category="Watches")
    _pos("P-1", "Khamrah", brand="Lattafa", category="Perfumes")

    plain = client.get(MAPPING).content.decode()
    suggested = client.get(MAPPING, {"tick": "suggested"}).content.decode()

    assert plain.count("data-not-online-hint") == 1
    assert "Tick the 1 suggested row(s)" in plain
    assert "checked" not in plain.split("<tbody")[1]
    assert suggested.split("<tbody")[1].count("checked") == 1
    assert PosProduct.objects.filter(not_online=True).count() == 0  # a hint, never automatic


@pytest.mark.django_db
def test_not_online_bulk_form_returns_without_the_tick_parameter(client, owner) -> None:  # type: ignore[no-untyped-def]
    _pos("W-1", "F-91W", brand="Casio", category="Watches")

    html = client.get(MAPPING, {"status": "unmapped", "tick": "suggested"}).content.decode()

    assert 'name="next" value="/admin-portal/pos/?status=unmapped"' in html


# --- access control ----------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["bulk-review/", "bulk-not-online/"])
def test_staff_cannot_use_the_bulk_endpoints(client, django_user_model, path) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user("staff", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    variant = mapped_variant(None)
    product = _pos("A-1", "Anything")

    assert client.get(MAPPING + path).status_code == 403
    response = client.post(
        MAPPING + path, {"pair": [f"{product.pk}:{variant.pk}"], "pos_ids": [product.pk]}
    )

    assert response.status_code == 403
    variant.refresh_from_db()
    product.refresh_from_db()
    assert variant.pos_sku is None and product.not_online is False


@pytest.mark.django_db
def test_anonymous_is_sent_to_login(client) -> None:  # type: ignore[no-untyped-def]
    assert client.get(BULK).status_code == 302
    assert client.post(BULK_NOT_ONLINE, {}).status_code == 302
