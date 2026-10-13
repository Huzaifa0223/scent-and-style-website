"""Stock edit forms warn that the POS overwrites hand edits on mapped variants."""

from __future__ import annotations

import pytest

from possync.tests.support import mapped_variant

WARNING = "POS updates will overwrite this"


@pytest.fixture
def owner(client, django_user_model):  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_superuser("owner", "o@example.com", "pw-not-used")
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_inventory_list_warns_only_for_mapped_variants(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant("POS-1", name="Mapped Perfume")
    mapped_variant(None, name="Loose Perfume")

    html = client.get("/admin-portal/inventory/").content.decode()

    assert html.count(WARNING) == 1


@pytest.mark.django_db
def test_inventory_list_has_no_warning_when_nothing_is_mapped(client, owner) -> None:  # type: ignore[no-untyped-def]
    mapped_variant(None)

    assert WARNING not in client.get("/admin-portal/inventory/").content.decode()


@pytest.mark.django_db
def test_product_edit_form_warns_on_the_stock_field_of_a_mapped_variant(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", name="Mapped Perfume")

    html = client.get(f"/admin-portal/products/{variant.product_id}/edit/").content.decode()

    assert html.count(WARNING) == 1
    stock_field = html.index("stock_quantity")
    assert 0 < html.index(WARNING) - stock_field < 1500  # next to the stock field


@pytest.mark.django_db
def test_product_edit_form_has_no_warning_for_an_unmapped_variant(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None)

    html = client.get(f"/admin-portal/products/{variant.product_id}/edit/").content.decode()

    assert WARNING not in html


@pytest.mark.django_db
def test_adjusting_a_mapped_variants_stock_says_the_pos_will_overwrite_it(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant("POS-1", stock=3)

    response = client.post(
        f"/admin-portal/inventory/{variant.pk}/adjust/", {"absolute_quantity": "8"}, follow=True
    )

    variant.refresh_from_db()
    assert variant.stock_quantity == 8  # the edit itself still works
    assert WARNING.encode() in response.content


@pytest.mark.django_db
def test_adjusting_an_unmapped_variants_stock_has_no_warning_message(client, owner) -> None:  # type: ignore[no-untyped-def]
    variant = mapped_variant(None, stock=3)

    response = client.post(
        f"/admin-portal/inventory/{variant.pk}/adjust/", {"absolute_quantity": "8"}, follow=True
    )

    assert b"stock set to 8" in response.content
    assert b"POS updates will overwrite" not in response.content
