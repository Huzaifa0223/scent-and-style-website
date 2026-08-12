from __future__ import annotations

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image as PILImage

from catalog.factories import ProductFactory, ProductImageFactory, ProductVariantFactory
from catalog.models import ProductImage


def _make_upload(
    name: str = "original.jpg", size: tuple[int, int] = (2000, 1000)
) -> SimpleUploadedFile:
    """Generates a real JPEG at runtime with Pillow — no binary fixtures
    committed to git (CLAUDE.md / roadmap Stage 2 acceptance gate 6)."""
    buffer = BytesIO()
    PILImage.new("RGB", size, color="blue").save(buffer, format="JPEG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/jpeg")


@pytest.mark.django_db
def test_alt_text_falls_back_to_product_name_when_blank() -> None:
    product = ProductFactory(name="Afnan 9PM Eau de Parfum")
    image = ProductImage.objects.create(product=product, image=_make_upload())
    assert image.alt_text == "Afnan 9PM Eau de Parfum"


@pytest.mark.django_db
def test_explicit_alt_text_is_not_overwritten() -> None:
    product = ProductFactory()
    image = ProductImage.objects.create(
        product=product, image=_make_upload(), alt_text="A custom description"
    )
    assert image.alt_text == "A custom description"


@pytest.mark.django_db
def test_first_image_auto_promotes_to_primary() -> None:
    product = ProductFactory()
    image = ProductImage.objects.create(product=product, image=_make_upload())
    assert image.is_primary is True


@pytest.mark.django_db
def test_second_image_does_not_auto_promote() -> None:
    product = ProductFactory()
    ProductImage.objects.create(product=product, image=_make_upload("one.jpg"))
    second = ProductImage.objects.create(product=product, image=_make_upload("two.jpg"))
    assert second.is_primary is False


@pytest.mark.django_db
def test_deleting_the_primary_image_promotes_the_next_by_position() -> None:
    product = ProductFactory()
    first = ProductImage.objects.create(product=product, image=_make_upload("one.jpg"), position=0)
    second = ProductImage.objects.create(product=product, image=_make_upload("two.jpg"), position=1)
    assert first.is_primary is True
    assert second.is_primary is False

    first.delete()

    second.refresh_from_db()
    assert second.is_primary is True


@pytest.mark.django_db
def test_deleting_a_non_primary_image_does_not_touch_the_primary() -> None:
    product = ProductFactory()
    first = ProductImage.objects.create(product=product, image=_make_upload("one.jpg"), position=0)
    second = ProductImage.objects.create(product=product, image=_make_upload("two.jpg"), position=1)
    second.delete()
    first.refresh_from_db()
    assert first.is_primary is True


@pytest.mark.django_db
def test_deleting_the_only_image_leaves_zero_images_without_error() -> None:
    """The promotion path's product.images.order_by(...).first() is None
    when the deleted image was the only one — must not crash, and must not
    leave anything behind to promote."""
    product = ProductFactory()
    only = ProductImage.objects.create(product=product, image=_make_upload())
    assert only.is_primary is True

    only.delete()

    assert product.images.count() == 0


@pytest.mark.django_db
def test_deleting_an_image_referenced_by_a_variant_nulls_the_variant_fk() -> None:
    """ProductVariant.image is SET_NULL — deleting the image a variant
    points at (its gallery hero) must null the FK, not leave it dangling."""
    product = ProductFactory()
    image = ProductImage.objects.create(product=product, image=_make_upload())
    variant = ProductVariantFactory(product=product, image=image)

    image.delete()

    variant.refresh_from_db()
    assert variant.image_id is None


@pytest.mark.django_db
def test_only_one_primary_image_per_product_at_db_level() -> None:
    product = ProductFactory()
    ProductImage.objects.create(product=product, image=_make_upload("one.jpg"))
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductImage.objects.create(product=product, image=_make_upload("two.jpg"), is_primary=True)


@pytest.mark.django_db
def test_upload_produces_three_derivatives_with_correct_dimensions() -> None:
    """Acceptance gate 6: thumb 200px / card 600px / full 1400px, longest
    edge, aspect ratio preserved. Source is 2000x1000 (2:1)."""
    product = ProductFactory()
    image = ProductImage.objects.create(product=product, image=_make_upload(size=(2000, 1000)))

    expected = {"thumb": (200, 100), "card": (600, 300), "full": (1400, 700)}
    for name, (expected_w, expected_h) in expected.items():
        for fmt in ("webp", "jpeg"):
            field = getattr(image, f"{name}_{fmt}")
            assert field, f"{name}_{fmt} was not generated"
            with field.open("rb") as handle:
                width, height = PILImage.open(handle).size
            assert (width, height) == (expected_w, expected_h), f"{name}_{fmt} wrong size"


@pytest.mark.django_db
def test_derivatives_not_regenerated_when_unrelated_field_changes() -> None:
    product = ProductFactory()
    image = ProductImage.objects.create(product=product, image=_make_upload())
    original_thumb_name = image.thumb_webp.name

    image.position = 5
    image.save(update_fields=["position"])

    image.refresh_from_db()
    assert image.thumb_webp.name == original_thumb_name


@pytest.mark.django_db
def test_factory_produces_a_valid_image_with_derivatives() -> None:
    image = ProductImageFactory()
    assert image.pk is not None
    assert image.thumb_webp
    assert image.is_primary is True
