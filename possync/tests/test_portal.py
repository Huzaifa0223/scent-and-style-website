"""Portal "POS mapping" pages: access control, upload, suggestions, confirm,
not-online, export, price differences, audit."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from catalog.models import ProductVariant
from possync.models import PosMappingEvent, PosProduct, PosSyncState
from possync.tests.support import mapped_variant

MAPPING = "/admin-portal/pos/"
HEADER = "sku,brand,name,category,price_rs,active\n"


@pytest.fixture
def owner(client, django_user_model):  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_superuser("owner", "o@example.com", "pw-not-used")
    client.force_login(user)
    return user


def _upload(client, text: str):  # type: ignore[no-untyped-def]
    return client.post(
        MAPPING + "upload/",
        {"csv_file": SimpleUploadedFile("pos.csv", text.encode(), content_type="text/csv")},
        follow=True,
    )


# --- access control ----------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_is_sent_to_login(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get(MAPPING)

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ["", "export/", "price-mismatches/"],
)
def test_staff_without_the_permission_gets_403(client, django_user_model, path) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user("staff", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)

    assert client.get(MAPPING + path).status_code == 403


@pytest.mark.django_db
def test_staff_cannot_post_mapping_actions_either(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    staff = django_user_model.objects.create_user("staff", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    product = PosProduct.objects.create(sku="A-1")
    variant = mapped_variant(None)

    response = client.post(f"{MAPPING}{product.pk}/map/", {"variant_id": variant.pk})

    assert response.status_code == 403
    variant.refresh_from_db()
    assert variant.pos_sku is None


@pytest.mark.django_db
def test_owner_sees_the_page_and_the_nav_link(client, owner) -> None:  # type: ignore[no-untyped-def]
    response = client.get(MAPPING)

    assert response.status_code == 200
    assert b"POS mapping" in response.content


# --- upload + suggestions ----------------------------------------------------


@pytest.mark.django_db
def test_upload_imports_rows_but_never_confirms_a_mapping(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None, name="Club De Nuit Intense Man", brand="Armaf")

    response = _upload(
        client, HEADER + "ARM-CDN,Armaf,Club De Nuit Intense Man 105ml,Perfumes,12500,yes\n"
    )

    assert response.status_code == 200
    assert PosProduct.objects.filter(sku="ARM-CDN").exists()
    variant.refresh_from_db()
    assert variant.pos_sku is None  # suggested, never auto-confirmed
    assert ProductVariant.objects.filter(pos_sku__isnull=False).count() == 0


@pytest.mark.django_db
def test_unmapped_row_shows_ranked_suggestions_with_scores(client, owner) -> None:  # type: ignore[no-untyped-def]
    right = mapped_variant(None, name="Club De Nuit Intense Man", brand="Armaf")
    mapped_variant(None, name="Khamrah", brand="Lattafa")
    _upload(client, HEADER + "ARM-CDN,Armaf,Club De Nuit Intense Man 105ml,Perfumes,12500,yes\n")

    html = client.get(MAPPING).content.decode()

    assert right.sku in html
    assert f'name="variant_id" value="{right.pk}"' in html  # a "Map" form for it
    assert "match 0." in html or "match 1." in html  # shows its score
    assert "Khamrah" not in html  # different brand/name is not suggested


@pytest.mark.django_db
def test_upload_without_a_file_is_a_message_not_an_error(client, owner) -> None:  # type: ignore[no-untyped-def]
    missing = client.post(MAPPING + "upload/", {}, follow=True)

    assert missing.status_code == 200
    assert b"Choose a POS product CSV" in missing.content
    assert PosProduct.objects.count() == 0


@pytest.mark.django_db
def test_upload_over_the_size_cap_is_refused(client, owner, settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("possync.portal_views.CSV_MAX_BYTES", 50)

    response = _upload(
        client, HEADER + "A-1,Armaf,Some long name that pushes past fifty bytes,P,1,yes\n"
    )

    assert b"larger than" in response.content
    assert PosProduct.objects.count() == 0


# --- confirm / unmap / not online -------------------------------------------


@pytest.mark.django_db
def test_confirming_maps_the_variant_and_writes_an_audit_row(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None)
    product = PosProduct.objects.create(sku="ARM-1", name="Khamrah")

    client.post(f"{MAPPING}{product.pk}/map/", {"variant_id": variant.pk})

    variant.refresh_from_db()
    assert variant.pos_sku == "ARM-1"
    event = PosMappingEvent.objects.get(action=PosMappingEvent.Action.MAPPED)
    assert (event.pos_sku, event.variant_sku, event.actor) == ("ARM-1", variant.sku, owner)


@pytest.mark.django_db
def test_a_variant_cannot_be_mapped_to_two_pos_skus(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("FIRST")
    second = PosProduct.objects.create(sku="SECOND")

    response = client.post(f"{MAPPING}{second.pk}/map/", {"variant_id": variant.pk}, follow=True)

    variant.refresh_from_db()
    assert variant.pos_sku == "FIRST"
    assert b"already mapped" in response.content


@pytest.mark.django_db
def test_a_pos_sku_cannot_be_mapped_to_two_variants(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("TAKEN")
    other = mapped_variant(None)
    product = PosProduct.objects.create(sku="TAKEN")

    response = client.post(f"{MAPPING}{product.pk}/map/", {"variant_id": other.pk}, follow=True)

    other.refresh_from_db()
    assert other.pos_sku is None
    assert b"already mapped to another variant" in response.content
    assert PosMappingEvent.objects.filter(action=PosMappingEvent.Action.MAPPED).count() == 0


@pytest.mark.django_db
def test_unmapping_clears_the_link_and_is_audited(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1")
    product = PosProduct.objects.create(sku="ARM-1")

    client.post(f"{MAPPING}{product.pk}/unmap/")

    variant.refresh_from_db()
    assert variant.pos_sku is None
    assert PosMappingEvent.objects.filter(action=PosMappingEvent.Action.UNMAPPED).count() == 1


@pytest.mark.django_db
def test_marking_not_sold_online_is_audited_and_reversible(client, owner) -> None:  # type: ignore[no-untyped-def]
    product = PosProduct.objects.create(sku="WATCH-1", name="Casio F-91W")

    client.post(f"{MAPPING}{product.pk}/not-online/", {"value": "1"})
    product.refresh_from_db()
    assert product.not_online is True

    client.post(f"{MAPPING}{product.pk}/not-online/", {"value": "0"})
    product.refresh_from_db()
    assert product.not_online is False
    actions = list(PosMappingEvent.objects.order_by("id").values_list("action", flat=True))
    assert actions == ["marked_not_online", "marked_online"]


@pytest.mark.django_db
def test_a_mapped_product_cannot_be_marked_not_online(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("ARM-1")
    product = PosProduct.objects.create(sku="ARM-1")

    response = client.post(f"{MAPPING}{product.pk}/not-online/", {"value": "1"}, follow=True)

    product.refresh_from_db()
    assert product.not_online is False
    assert b"Remove the mapping first" in response.content


@pytest.mark.django_db
def test_confirming_a_not_online_product_clears_the_flag(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None)
    product = PosProduct.objects.create(sku="ARM-1", not_online=True)

    client.post(f"{MAPPING}{product.pk}/map/", {"variant_id": variant.pk})

    product.refresh_from_db()
    assert product.not_online is False


# --- filters / export / price differences -----------------------------------


@pytest.mark.django_db
def test_filters_split_unmapped_mapped_and_not_online(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("MAPPED-1")
    PosProduct.objects.create(sku="MAPPED-1", name="Mapped one")
    PosProduct.objects.create(sku="LOOSE-1", name="Loose one")
    PosProduct.objects.create(sku="WATCH-1", name="Watch one", not_online=True)

    def listed(status: str) -> str:
        return client.get(MAPPING, {"status": status}).content.decode()

    assert "LOOSE-1" in listed("unmapped") and "MAPPED-1" not in listed("unmapped")
    assert "WATCH-1" not in listed("unmapped")
    assert "MAPPED-1" in listed("mapped") and "LOOSE-1" not in listed("mapped")
    assert "WATCH-1" in listed("not_online") and "LOOSE-1" not in listed("not_online")
    everything = listed("all")
    assert all(sku in everything for sku in ("MAPPED-1", "LOOSE-1", "WATCH-1"))


@pytest.mark.django_db
def test_export_lists_the_mapping_and_escapes_formulas(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("ARM-1", price="12500.00", name="Khamrah")
    PosProduct.objects.create(sku="ARM-1", brand="Lattafa", name="Khamrah", price=Decimal("12000"))
    PosProduct.objects.create(sku="X-2", name='=HYPERLINK("http://evil")')

    response = client.get(MAPPING + "export/")

    assert response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    by_sku = {row["sku"]: row for row in rows}
    assert by_sku["ARM-1"]["website_sku"] == variant.sku
    assert by_sku["ARM-1"]["website_price_rs"] == "12500.00"
    assert by_sku["X-2"]["name"].startswith("'=")


@pytest.mark.django_db
def test_price_differences_lists_only_mismatches_and_changes_nothing(client, owner) -> None:  # type: ignore[no-untyped-def]
    differs = mapped_variant("A", price="1000.00", name="Differs")
    same = mapped_variant("B", price="500.00", name="Same")
    mapped_variant("C", price="700.00", name="Never reported")
    ProductVariant.objects.filter(pk=differs.pk).update(pos_price=Decimal("1200.00"))
    ProductVariant.objects.filter(pk=same.pk).update(pos_price=Decimal("500.00"))

    html = client.get(MAPPING + "price-mismatches/").content.decode()

    assert "Differs" in html
    assert "Same" not in html and "Never reported" not in html
    differs.refresh_from_db()
    assert differs.price == Decimal("1000.00")  # a human fixes it; we never do


# --- order cutoff + status ---------------------------------------------------


@pytest.mark.django_db
def test_owner_can_move_the_web_order_cutoff_and_it_is_audited(client, owner) -> None:  # type: ignore[no-untyped-def]
    client.post(MAPPING + "orders-since/", {"orders_since": "2026-01-02T09:30"})

    state = PosSyncState.objects.get(pk=1)
    assert timezone.localtime(state.orders_since).strftime("%Y-%m-%d %H:%M") == "2026-01-02 09:30"
    assert PosMappingEvent.objects.filter(action=PosMappingEvent.Action.ORDERS_CUTOFF).exists()


@pytest.mark.django_db
def test_invalid_cutoff_is_rejected(client, owner) -> None:  # type: ignore[no-untyped-def]
    before = PosSyncState.objects.get_or_create(pk=1)[0].orders_since

    response = client.post(MAPPING + "orders-since/", {"orders_since": "not a date"}, follow=True)

    assert b"valid date" in response.content
    assert PosSyncState.objects.get(pk=1).orders_since == before


@pytest.mark.django_db
def test_oversold_items_from_the_last_sync_are_shown(client, owner) -> None:  # type: ignore[no-untyped-def]
    state = PosSyncState.objects.get_or_create(pk=1)[0]
    state.last_result = {
        "applied": 1,
        "unchanged": 0,
        "unmapped": [],
        "oversold": [{"sku": "ARM-1", "short": 3}],
    }
    state.save()

    html = client.get(MAPPING).content.decode()

    assert "Oversold" in html
    assert "ARM-1" in html and "short by 3" in html


@pytest.mark.django_db
def test_mapping_page_query_count_stays_flat_as_rows_grow(client, owner) -> None:  # type: ignore[no-untyped-def]
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def count_queries() -> int:
        # Warm the DB-backed caches first: creating rows in between measurements
        # invalidates store/session cache entries, and re-filling those is
        # unrelated to how many rows the page lists.
        client.get(MAPPING)
        with CaptureQueriesContext(connection) as queries:
            assert client.get(MAPPING).status_code == 200
        return len(queries)

    for index in range(3):
        mapped_variant(None, name=f"Perfume {index}", brand="Armaf")
        PosProduct.objects.create(sku=f"P-{index}", brand="Armaf", name=f"Perfume {index} 100ml")
    at_three = count_queries()
    for index in range(3, 20):
        mapped_variant(None, name=f"Perfume {index}", brand="Armaf")
        PosProduct.objects.create(sku=f"P-{index}", brand="Armaf", name=f"Perfume {index} 100ml")
    at_twenty = count_queries()

    assert at_twenty == at_three, f"{at_three} queries at 3 rows, {at_twenty} at 20"
