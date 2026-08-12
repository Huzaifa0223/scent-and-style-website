"""Product create/edit views and the variant formset (Stage 3).

Gate 1: create a product with three variants across two attributes and
publish it, without touching Django admin. Gate 2: deleting the last
variant is refused with a clean message, not an IntegrityError. The rest
cover the design points raised in advisor review before this was built:
default-variant auto-promotion on delete, and a duplicate attribute set
that only appears once one variant's *unmodified* row is accounted for.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.factories import (
    AttributeDefinitionFactory,
    AttributeValueFactory,
    CategoryFactory,
    ProductFactory,
    ProductVariantFactory,
    TagFactory,
)
from catalog.models import Product, ProductVariant, VariantAttributeValue
from portal.product_forms import ProductVariantForm


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


def _management_form(prefix: str, *, total: int, initial: int) -> dict[str, str]:
    return {f"{prefix}-TOTAL_FORMS": str(total), f"{prefix}-INITIAL_FORMS": str(initial)}


def _variant_form_data(
    prefix: str,
    index: int,
    *,
    sku: str,
    price: str = "10.00",
    stock_quantity: str = "5",
    low_stock_threshold: str = "3",
    attribute_values: list[int] | None = None,
    is_default: bool = False,
    is_active: bool = True,
    position: int = 0,
    delete: bool = False,
    variant_id: int | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        f"{prefix}-{index}-sku": sku,
        f"{prefix}-{index}-price": price,
        f"{prefix}-{index}-compare_at_price": "",
        f"{prefix}-{index}-stock_quantity": stock_quantity,
        f"{prefix}-{index}-low_stock_threshold": low_stock_threshold,
        f"{prefix}-{index}-position": str(position),
        f"{prefix}-{index}-attribute_values": attribute_values or [],
    }
    if is_default:
        data[f"{prefix}-{index}-is_default"] = "on"
    if is_active:
        data[f"{prefix}-{index}-is_active"] = "on"
    if delete:
        data[f"{prefix}-{index}-DELETE"] = "on"
    if variant_id is not None:
        data[f"{prefix}-{index}-id"] = str(variant_id)
    return data


def _product_form_payload(product: Product, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": product.name,
        "category": product.category_id,
        "subcategory": product.subcategory_id or "",
        "brand": product.brand_id or "",
        "short_description": product.short_description,
        "description": product.description,
        "tags": list(product.tags.values_list("pk", flat=True)),
        "status": product.status,
        "meta_title": product.meta_title,
        "meta_description": product.meta_description,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_gate1_create_product_with_three_variants_across_two_attributes_and_publish(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    category = CategoryFactory()
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    size_100 = AttributeValueFactory(definition=size, value="100ml")
    color = AttributeDefinitionFactory(name="Color")
    color_red = AttributeValueFactory(definition=color, value="Red")

    data: dict[str, Any] = {
        "name": "Gate One Perfume",
        "category": category.pk,
        "subcategory": "",
        "brand": "",
        "short_description": "",
        "description": "",
        "tags": [],
        "status": Product.Status.PUBLISHED,
        "meta_title": "",
        "meta_description": "",
    }
    data.update(_management_form("variants", total=3, initial=0))
    data.update(
        _variant_form_data(
            "variants",
            0,
            sku="GATE1-50-RED",
            attribute_values=[size_50.pk, color_red.pk],
            is_default=True,
        )
    )
    data.update(
        _variant_form_data(
            "variants", 1, sku="GATE1-100-RED", attribute_values=[size_100.pk, color_red.pk]
        )
    )
    data.update(
        _variant_form_data("variants", 2, sku="GATE1-50-PLAIN", attribute_values=[size_50.pk])
    )

    response = client.post("/admin-portal/products/create/", data)

    assert response.status_code == 302
    product = Product.objects.get(name="Gate One Perfume")
    assert product.status == Product.Status.PUBLISHED
    assert product.variants.count() == 3
    skus = set(product.variants.values_list("sku", flat=True))
    assert skus == {"GATE1-50-RED", "GATE1-100-RED", "GATE1-50-PLAIN"}
    assert product.variants.filter(is_default=True).count() == 1


@pytest.mark.django_db
def test_gate2_deleting_the_last_variant_is_refused_with_a_clean_message(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    variant = product.variants.get()

    data = _product_form_payload(product)
    data.update(_management_form("variants", total=1, initial=1))
    data.update(
        _variant_form_data(
            "variants",
            0,
            sku=variant.sku,
            price=str(variant.price),
            is_default=True,
            delete=True,
            variant_id=variant.pk,
        )
    )

    response = client.post(f"/admin-portal/products/{product.pk}/edit/", data)

    assert response.status_code == 200
    assert b"at least one variant" in response.content
    assert ProductVariant.objects.filter(pk=variant.pk).exists()


@pytest.mark.django_db
def test_edit_deleting_the_default_variant_auto_promotes_the_survivor(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """End-to-end proof of the whole assembled mechanism: clean() auto-
    promotes the surviving form, the view saves survivors before deletes,
    and ProductVariant.delete()'s own promotion guard correctly no-ops
    because a new default is already in place by the time the old one is
    deleted."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    old_default = product.variants.get(is_default=True)
    survivor = ProductVariantFactory(product=product, sku="SURVIVOR", price=Decimal("12.00"))

    data = _product_form_payload(product)
    data.update(_management_form("variants", total=2, initial=2))
    data.update(
        _variant_form_data(
            "variants",
            0,
            sku=old_default.sku,
            price=str(old_default.price),
            is_default=True,
            delete=True,
            variant_id=old_default.pk,
        )
    )
    data.update(
        _variant_form_data(
            "variants", 1, sku=survivor.sku, price=str(survivor.price), variant_id=survivor.pk
        )
    )

    response = client.post(f"/admin-portal/products/{product.pk}/edit/", data)

    assert response.status_code == 302
    assert not ProductVariant.objects.filter(pk=old_default.pk).exists()
    survivor.refresh_from_db()
    assert survivor.is_default is True


@pytest.mark.django_db
def test_variant_form_initial_attribute_values_reflect_existing_rows() -> None:
    """Without this, an edit page would render every existing variant's
    attribute checkboxes unchecked, and resubmitting an untouched row would
    silently clear its attributes on save."""
    variant = ProductVariantFactory(sku="INITIAL-TEST")
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    VariantAttributeValue.objects.create(variant=variant, value=size_50)

    form = ProductVariantForm(instance=variant)

    assert list(form.fields["attribute_values"].initial) == [size_50.pk]


@pytest.mark.django_db
def test_edit_rejects_a_new_collision_even_when_the_other_variant_is_unmodified(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """The blocking item from advisor review: variant "untouched" is
    resubmitted with exactly the attribute_values it already has in the DB
    (what a browser would echo back for a row the merchant never touched,
    given ProductVariantForm.__init__ populates initial from it). Giving
    default_variant that same set must be caught by clean(), not surface as
    an IntegrityError from sync_attribute_signature()."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    default_variant = product.variants.get(is_default=True)
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    untouched = ProductVariantFactory(product=product, sku="UNTOUCHED", price=Decimal("10.00"))
    VariantAttributeValue.objects.create(variant=untouched, value=size_50)

    data = _product_form_payload(product)
    data.update(_management_form("variants", total=2, initial=2))
    data.update(
        _variant_form_data(
            "variants",
            0,
            sku=default_variant.sku,
            price=str(default_variant.price),
            is_default=True,
            attribute_values=[size_50.pk],
            variant_id=default_variant.pk,
        )
    )
    data.update(
        _variant_form_data(
            "variants",
            1,
            sku=untouched.sku,
            price=str(untouched.price),
            attribute_values=[size_50.pk],
            variant_id=untouched.pk,
        )
    )

    response = client.post(f"/admin-portal/products/{product.pk}/edit/", data)

    assert response.status_code == 200
    assert b"already has this exact combination" in response.content
    default_variant.refresh_from_db()
    assert default_variant.attribute_signature == ""


@pytest.mark.django_db
def test_edit_page_query_count_stays_flat_as_variant_count_grows(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Roadmap Stage 3's own named trap: "the variant formset is where N+1
    queries enter the codebase." Same technique as the product list's gate
    5 (portal/tests/test_product_list.py) — compare captured query counts
    at two different variant counts rather than asserting a fixed number."""
    _login_owner(client, django_user_model)
    product = ProductFactory()  # 1 variant (the auto-created default)
    edit_url = f"/admin-portal/products/{product.pk}/edit/"

    client.get(edit_url)  # warm up StoreSettings.load() etc., as gate 5 does

    with CaptureQueriesContext(connection) as captured_at_1:
        response = client.get(edit_url)
    assert response.status_code == 200
    queries_at_1 = len(captured_at_1)

    for i in range(4):
        ProductVariantFactory(product=product, sku=f"N1-EXTRA-{i}")
    assert product.variants.count() == 5
    with CaptureQueriesContext(connection) as captured_at_5:
        response = client.get(edit_url)
    assert response.status_code == 200
    queries_at_5 = len(captured_at_5)

    assert queries_at_5 == queries_at_1, (
        f"query count grew with variant count: {queries_at_1} at 1 variant, "
        f"{queries_at_5} at 5 — likely an N+1"
    )


@pytest.mark.django_db
def test_create_page_renders(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    response = client.get("/admin-portal/products/create/")
    assert response.status_code == 200
    assert b"New product" in response.content


@pytest.mark.django_db
def test_edit_page_renders_with_existing_variant_data(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    variant = product.variants.get()

    response = client.get(f"/admin-portal/products/{product.pk}/edit/")

    assert response.status_code == 200
    assert variant.sku.encode() in response.content


@pytest.mark.django_db
def test_edit_changing_a_variants_attribute_values_syncs_added_and_removed_rows(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Exercises both branches of _sync_attribute_values: dropping a value
    the variant no longer submits, and adding one it newly does."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    variant = product.variants.get(is_default=True)
    size = AttributeDefinitionFactory(name="Size")
    size_50 = AttributeValueFactory(definition=size, value="50ml")
    size_100 = AttributeValueFactory(definition=size, value="100ml")
    VariantAttributeValue.objects.create(variant=variant, value=size_50)

    data = _product_form_payload(product)
    data.update(_management_form("variants", total=1, initial=1))
    data.update(
        _variant_form_data(
            "variants",
            0,
            sku=variant.sku,
            price=str(variant.price),
            is_default=True,
            attribute_values=[size_100.pk],
            variant_id=variant.pk,
        )
    )

    response = client.post(f"/admin-portal/products/{product.pk}/edit/", data)

    assert response.status_code == 302
    variant.refresh_from_db()
    assert variant.attribute_signature == str(size_100.pk)
    assert set(variant.variant_attribute_values.values_list("value_id", flat=True)) == {size_100.pk}


@pytest.mark.django_db
def test_product_tags_are_saved_via_the_product_form(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """form.save() (commit=True, the default) must handle the tags M2M —
    using commit=False here without an explicit save_m2m() call would
    silently drop them."""
    _login_owner(client, django_user_model)
    category = CategoryFactory()
    tag_a = TagFactory(name="Bestseller")
    tag_b = TagFactory(name="New")

    data: dict[str, Any] = {
        "name": "Tagged Product",
        "category": category.pk,
        "subcategory": "",
        "brand": "",
        "short_description": "",
        "description": "",
        "tags": [tag_a.pk, tag_b.pk],
        "status": Product.Status.DRAFT,
        "meta_title": "",
        "meta_description": "",
    }
    data.update(_management_form("variants", total=1, initial=0))
    data.update(_variant_form_data("variants", 0, sku="TAGGED-SKU"))

    response = client.post("/admin-portal/products/create/", data)

    assert response.status_code == 302
    product = Product.objects.get(name="Tagged Product")
    assert set(product.tags.values_list("pk", flat=True)) == {tag_a.pk, tag_b.pk}
