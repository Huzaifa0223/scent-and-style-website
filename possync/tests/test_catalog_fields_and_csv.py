"""ProductVariant.pos_sku/pos_price and the POS product CSV import."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from catalog.factories import ProductFactory
from catalog.models import ProductVariant
from possync.models import PosMappingEvent, PosProduct
from possync.services import csv_safe, import_pos_csv

HEADER = "sku,brand,name,category,price_rs,active\n"


# --- ProductVariant fields --------------------------------------------------


@pytest.mark.django_db
def test_pos_sku_is_unique_when_set() -> None:
    first = ProductFactory().variants.get()
    second = ProductFactory().variants.get()
    ProductVariant.objects.filter(pk=first.pk).update(pos_sku="DUP")

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductVariant.objects.filter(pk=second.pk).update(pos_sku="DUP")


@pytest.mark.django_db
def test_many_variants_can_be_unmapped_at_once() -> None:
    for _ in range(3):
        ProductFactory()

    assert ProductVariant.objects.filter(pos_sku__isnull=True).count() == 3


@pytest.mark.django_db
def test_blank_pos_sku_is_rejected_so_null_is_the_only_unmapped_value() -> None:
    variant = ProductFactory().variants.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductVariant.objects.filter(pk=variant.pk).update(pos_sku="")


@pytest.mark.django_db
def test_pos_price_is_optional_and_informational() -> None:
    variant = ProductFactory(default_variant_price=Decimal("500.00")).variants.get()

    assert variant.pos_price is None
    ProductVariant.objects.filter(pk=variant.pk).update(pos_price=Decimal("450.00"))
    variant.refresh_from_db()
    assert (variant.price, variant.pos_price) == (Decimal("500.00"), Decimal("450.00"))


# --- CSV import -------------------------------------------------------------


@pytest.mark.django_db
def test_import_creates_products_and_records_an_audit_event() -> None:
    raw = (
        HEADER + "ARM-1,Armaf,Club De Nuit,Perfumes,12500,yes\nWAT-1,Casio,F-91W,Watches,4500,1\n"
    ).encode()

    result = import_pos_csv(raw, actor=None)

    assert (result.created, result.updated, result.errors) == (2, 0, [])
    product = PosProduct.objects.get(sku="ARM-1")
    assert (product.brand, product.name, product.category) == ("Armaf", "Club De Nuit", "Perfumes")
    assert product.price == Decimal("12500.00")
    assert product.active is True
    assert PosMappingEvent.objects.filter(action=PosMappingEvent.Action.CSV_IMPORT).count() == 1


@pytest.mark.django_db
def test_import_updates_existing_rows_and_keeps_admin_decisions() -> None:
    PosProduct.objects.create(sku="WAT-1", name="Old", not_online=True)

    result = import_pos_csv((HEADER + "WAT-1,Casio,F-91W,Watches,4500,yes\n").encode(), actor=None)

    assert (result.created, result.updated) == (0, 1)
    product = PosProduct.objects.get(sku="WAT-1")
    assert product.name == "F-91W"
    assert product.not_online is True  # never overwritten by a CSV


@pytest.mark.django_db
def test_import_accepts_bom_case_insensitive_headers_and_rs_formatting() -> None:
    raw = '﻿SKU,Brand,NAME,Price_Rs\nA-1,Armaf,Tres,"Rs. 12,500"\n'.encode()

    result = import_pos_csv(raw, actor=None)

    assert result.errors == []
    assert PosProduct.objects.get(sku="A-1").price == Decimal("12500.00")


@pytest.mark.django_db
def test_bad_rows_are_reported_and_good_rows_still_applied() -> None:
    raw = (
        HEADER
        + "OK-1,Armaf,Fine,Perfumes,100,yes\n"
        + ",Armaf,No sku,Perfumes,100,yes\n"
        + "BAD-PRICE,Armaf,x,Perfumes,abc,yes\n"
        + "NEG,Armaf,x,Perfumes,-5,yes\n"
        + "BAD-ACTIVE,Armaf,x,Perfumes,100,maybe\n"
        + "OK-1,Armaf,Duplicate,Perfumes,100,yes\n"
        + "OK-2,Armaf,Fine too,Perfumes,,no\n"
    ).encode()

    result = import_pos_csv(raw, actor=None)

    assert set(PosProduct.objects.values_list("sku", flat=True)) == {"OK-1", "OK-2"}
    assert len(result.errors) == 5
    assert any("Line 3" in e and "sku is empty" in e for e in result.errors)
    assert any("Line 4" in e and "price" in e for e in result.errors)
    assert any("duplicate sku" in e for e in result.errors)
    assert PosProduct.objects.get(sku="OK-2").active is False
    assert PosProduct.objects.get(sku="OK-1").name == "Fine"  # first duplicate kept


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "empty"),
        (b"brand,name\nArmaf,x\n", "sku"),
        (b"\xff\xfe\x00bad", "UTF-8"),
    ],
)
def test_unusable_files_are_rejected_without_touching_the_database(
    raw: bytes, message: str
) -> None:
    result = import_pos_csv(raw, actor=None)

    assert result.rows_ok == 0
    assert message.lower() in result.errors[0].lower()
    assert PosProduct.objects.count() == 0
    assert PosMappingEvent.objects.count() == 0


def test_csv_export_neutralises_spreadsheet_formulas() -> None:
    assert csv_safe('=HYPERLINK("http://evil")') == '\'=HYPERLINK("http://evil")'
    assert csv_safe("+1") == "'+1"
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("Armaf") == "Armaf"
    assert csv_safe(None) == ""
