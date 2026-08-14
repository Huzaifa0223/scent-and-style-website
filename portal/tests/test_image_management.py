"""Product image management (Stage 3): upload, drag-reorder, primary
selection, delete, replace.

The N+1 test below is written before the feature it measures, per the
lesson from the variant formset: each image row shows which variants use
it as their hero (ProductVariant.image, related_name="variants") so a
merchant sees what they'd lose *before* deleting, not just after — and
that reverse-FK read is exactly the kind of per-row query the roadmap's
formset N+1 trap warns about, so it needs to be prefetched from the start.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from PIL import Image as PILImage

from catalog.factories import ProductFactory, ProductImageFactory, ProductVariantFactory
from catalog.models import ProductImage
from core.config import MAX_IMAGE_UPLOAD_BYTES
from portal.image_forms import ProductImageUploadForm


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


def _make_upload(name: str = "upload.jpg", color: str = "blue") -> SimpleUploadedFile:
    """Generates a real JPEG at runtime with Pillow — no binary fixtures
    committed to git (CLAUDE.md / roadmap Stage 2 acceptance gate 6)."""
    buffer = BytesIO()
    PILImage.new("RGB", (400, 400), color=color).save(buffer, format="JPEG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/jpeg")


@pytest.mark.django_db
def test_edit_page_query_count_stays_flat_as_image_count_grows(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Same technique as gate 5 (product list) and the variant formset's
    own regression test: compare captured query counts at two image
    counts, not a hardcoded number."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    edit_url = f"/admin-portal/products/{product.pk}/edit/"

    image = ProductImageFactory(product=product)
    ProductVariantFactory(product=product, sku="HERO-1", image=image)

    client.get(edit_url)  # warm up StoreSettings.load() etc., as gate 5 does

    with CaptureQueriesContext(connection) as captured_at_1:
        response = client.get(edit_url)
    assert response.status_code == 200
    queries_at_1 = len(captured_at_1)

    for i in range(4):
        extra_image = ProductImageFactory(product=product)
        ProductVariantFactory(product=product, sku=f"HERO-EXTRA-{i}", image=extra_image)
    assert product.images.count() == 5
    with CaptureQueriesContext(connection) as captured_at_5:
        response = client.get(edit_url)
    assert response.status_code == 200
    queries_at_5 = len(captured_at_5)

    assert queries_at_5 == queries_at_1, (
        f"query count grew with image count: {queries_at_1} at 1 image, "
        f"{queries_at_5} at 5 — likely an N+1"
    )


@pytest.mark.django_db
def test_upload_adds_an_image(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/upload/",
        {"image": _make_upload(), "alt_text": "A new gallery shot"},
    )

    assert response.status_code == 302
    assert product.images.filter(alt_text="A new gallery shot").exists()


@pytest.mark.django_db
def test_gate4_a_jpg_named_file_with_a_non_image_payload_is_rejected(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """§41 / roadmap Stage 13 gate 4. Django's ``forms.ImageField``
    (auto-derived from ``ProductImage.image``'s ``models.ImageField`` by
    ``ProductImageUploadForm``) opens the upload with Pillow and calls
    ``.verify()`` — a real content check, not an extension check — so a
    plain-text payload with a ``.jpg`` name is rejected here, not because
    of its extension but because Pillow can't decode it as an image.
    """
    _login_owner(client, django_user_model)
    product = ProductFactory()
    fake_image = SimpleUploadedFile(
        "totally-a-photo.jpg", b"this is not image data, just text", content_type="image/jpeg"
    )

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/upload/",
        {"image": fake_image, "alt_text": "Should not be saved"},
    )

    assert response.status_code == 302
    assert not product.images.exists()


def test_gate4_an_oversized_image_is_rejected() -> None:
    """§41: a size cap alongside the content check — a large-but-genuine
    image must not reach synchronous derivative generation
    (core/images.py) uncapped.

    Exercised directly against the form (not the HTTP endpoint): the
    Django test client re-serializes an uploaded file to real multipart
    bytes and the server re-derives ``.size`` from that wire content, so
    a client-side ``.size`` override has no effect on it — this is the
    standard way Django's own test suite proves a size-validator fires,
    without actually generating an 8 MB+ payload.
    """
    oversized = _make_upload()
    oversized.size = MAX_IMAGE_UPLOAD_BYTES + 1

    form = ProductImageUploadForm(data={"alt_text": "Too big"}, files={"image": oversized})

    assert not form.is_valid()
    assert "image" in form.errors


@pytest.mark.django_db
def test_gate3_reordering_persists_and_survives_a_reload(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    first = ProductImageFactory(product=product, position=0)
    second = ProductImageFactory(product=product, position=1)
    third = ProductImageFactory(product=product, position=2)

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/reorder/",
        {"order": [third.pk, first.pk, second.pk]},
    )
    assert response.status_code == 302

    third.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert (third.position, first.position, second.position) == (0, 1, 2)

    # Survives a reload: a fresh GET reflects the DB state, not a cached one.
    response = client.get(f"/admin-portal/products/{product.pk}/edit/")
    assert response.status_code == 200
    ordered_pks = [image.pk for image in product.images.all()]
    assert ordered_pks == [third.pk, first.pk, second.pk]


@pytest.mark.django_db
def test_reorder_and_re_primary_in_one_submit_succeeds(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """The scenario migration 0005 exists for: changing which image is
    primary while also reordering, in one POST — must not raise
    IntegrityError, even though the old and new primary are briefly both
    True/both False depending on statement order within the transaction."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    old_primary = ProductImageFactory(product=product, position=0)
    new_primary = ProductImageFactory(product=product, position=1)
    assert old_primary.is_primary is True

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/reorder/",
        {"order": [new_primary.pk, old_primary.pk], "primary_image": str(new_primary.pk)},
    )

    assert response.status_code == 302
    old_primary.refresh_from_db()
    new_primary.refresh_from_db()
    assert old_primary.is_primary is False
    assert new_primary.is_primary is True
    assert product.images.filter(is_primary=True).count() == 1
    assert (new_primary.position, old_primary.position) == (0, 1)


@pytest.mark.django_db
def test_deleting_an_image_nulls_the_variant_fk_and_warns_the_merchant(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Mirrors catalog's test_deleting_an_image_referenced_by_a_variant_
    nulls_the_variant_fk (Stage 2) at the portal level — the formset/view
    path must behave identically to the direct-delete path — plus the
    merchant-visible warning naming what was affected.

    Deletes the *primary* image while a second, non-primary image survives,
    so ProductImage.delete()'s promotion guard and the variant's SET_NULL
    both fire in the same call — the combination the direct-delete test
    doesn't exercise (it deletes the only image), and the one the reorder
    handler's re-primary logic depends on staying correct."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    image = ProductImageFactory(product=product, position=0)  # auto-primary
    survivor = ProductImageFactory(product=product, position=1, is_primary=False)
    variant = ProductVariantFactory(product=product, sku="HERO-VARIANT", image=image)

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/{image.pk}/delete/", follow=True
    )

    assert response.status_code == 200
    assert not ProductImage.objects.filter(pk=image.pk).exists()
    variant.refresh_from_db()
    assert variant.image_id is None
    survivor.refresh_from_db()
    assert survivor.is_primary is True
    assert product.images.filter(is_primary=True).count() == 1
    assert b"HERO-VARIANT" in response.content
    assert b"Removed as the hero image for" in response.content


@pytest.mark.django_db
def test_deleting_an_unreferenced_image_shows_no_warning(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    image = ProductImageFactory(product=product)

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/{image.pk}/delete/", follow=True
    )

    assert response.status_code == 200
    assert b"Removed as the hero image for" not in response.content


@pytest.mark.django_db
def test_staff_without_delete_permission_cannot_delete_an_image(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """The Staff group has add/change but not delete on catalog
    (accounts/permissions.py) — reorder/upload go through change/add, but
    delete is its own view specifically so this boundary holds."""
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    product = ProductFactory()
    image = ProductImageFactory(product=product)

    response = client.post(f"/admin-portal/products/{product.pk}/images/{image.pk}/delete/")

    assert response.status_code == 403
    assert ProductImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_replace_swaps_the_file_and_keeps_position_and_primary(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    ProductImageFactory(product=product, position=0)  # auto-primary; keeps the row below from it
    image = ProductImageFactory(product=product, position=3, is_primary=False)
    original_name = image.image.name

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/{image.pk}/replace/",
        {"image": _make_upload("replacement.jpg", color="red")},
    )

    assert response.status_code == 302
    image.refresh_from_db()
    assert image.image.name != original_name
    assert image.position == 3
    assert image.is_primary is False


@pytest.mark.django_db
def test_upload_with_an_invalid_file_shows_an_error_and_adds_nothing(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Asserts on the messages framework's level, not the message's exact
    wording — the wording is free to change without breaking this test."""
    _login_owner(client, django_user_model)
    product = ProductFactory()

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/upload/",
        {"image": SimpleUploadedFile("not-an-image.txt", b"hello", content_type="text/plain")},
        follow=True,
    )

    assert response.status_code == 200
    assert product.images.count() == 0
    levels = [message.level_tag for message in get_messages(response.wsgi_request)]
    assert levels == ["error"]


@pytest.mark.django_db
def test_delete_under_the_wrong_product_pk_returns_404(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """The pk/image_pk pair must be validated together — otherwise a staff
    user could delete an image on any product by supplying a mismatched
    pair (the product pk of one they can act on, the image_pk of one they
    can't)."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    other_product = ProductFactory()
    image = ProductImageFactory(product=other_product)

    response = client.post(f"/admin-portal/products/{product.pk}/images/{image.pk}/delete/")

    assert response.status_code == 404
    assert ProductImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_replace_under_the_wrong_product_pk_returns_404(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    other_product = ProductFactory()
    image = ProductImageFactory(product=other_product)
    original_name = image.image.name

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/{image.pk}/replace/",
        {"image": _make_upload("replacement.jpg", color="red")},
    )

    assert response.status_code == 404
    image.refresh_from_db()
    assert image.image.name == original_name


@pytest.mark.django_db
def test_reorder_rejects_an_image_id_belonging_to_another_product(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    own_image = ProductImageFactory(product=product, position=0)
    other_product = ProductFactory()
    foreign_image = ProductImageFactory(product=other_product, position=0)

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/reorder/",
        {"order": [foreign_image.pk, own_image.pk]},
    )

    assert response.status_code == 400
    own_image.refresh_from_db()
    assert own_image.position == 0  # untouched


@pytest.mark.django_db
def test_reorder_rejects_a_primary_selection_belonging_to_another_product(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()
    own_image = ProductImageFactory(product=product, position=0)
    other_product = ProductFactory()
    foreign_image = ProductImageFactory(product=other_product, position=0)

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/reorder/",
        {"order": [own_image.pk], "primary_image": str(foreign_image.pk)},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_reorder_with_an_omitted_image_does_not_collide_positions(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """A submitted `order` that doesn't list every image (a stale page, a
    partial submit) must not leave the omitted image on its old position —
    that collides with whatever the submitted images were just reassigned
    to. The omitted image should land after the submitted ones instead."""
    _login_owner(client, django_user_model)
    product = ProductFactory()
    first = ProductImageFactory(product=product, position=0)
    second = ProductImageFactory(product=product, position=1)
    third = ProductImageFactory(product=product, position=2)  # omitted from the submit below

    response = client.post(
        f"/admin-portal/products/{product.pk}/images/reorder/",
        {"order": [second.pk, first.pk]},
    )

    assert response.status_code == 302
    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    positions = {second.position, first.position, third.position}
    assert len(positions) == 3, "positions collided after an incomplete reorder submit"
    assert (second.position, first.position) == (0, 1)
    assert third.position == 2
