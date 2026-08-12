from __future__ import annotations

import pytest

from catalog.factories import BrandFactory
from catalog.models import Brand


@pytest.mark.django_db
def test_slug_generated_from_name_when_blank() -> None:
    brand = Brand.objects.create(name="Afnan Perfumes")
    assert brand.slug == "afnan-perfumes"


@pytest.mark.django_db
def test_slug_collision_gets_a_suffix() -> None:
    Brand.objects.create(name="Afnan Perfumes")
    second = Brand.objects.create(name="Afnan Perfumes")
    assert second.slug == "afnan-perfumes-2"


@pytest.mark.django_db
def test_explicit_slug_is_not_overwritten() -> None:
    brand = Brand.objects.create(name="Afnan Perfumes", slug="custom-slug")
    assert brand.slug == "custom-slug"


@pytest.mark.django_db
def test_name_change_does_not_change_an_existing_slug() -> None:
    """Slugs are stable — a rename must not silently break an existing
    link (roadmap Stage 2 / Stage 12's redirect mechanism depends on this
    holding)."""
    brand = Brand.objects.create(name="Afnan Perfumes")
    original_slug = brand.slug
    brand.name = "Afnan Perfumes Renamed"
    brand.save()
    assert brand.slug == original_slug


@pytest.mark.django_db
def test_factory_produces_a_valid_brand() -> None:
    brand = BrandFactory()
    assert brand.pk is not None
    assert brand.slug
