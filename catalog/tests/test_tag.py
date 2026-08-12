from __future__ import annotations

import pytest

from catalog.factories import TagFactory
from catalog.models import Tag


@pytest.mark.django_db
def test_slug_generated_from_name() -> None:
    tag = Tag.objects.create(name="Gift Sets")
    assert tag.slug == "gift-sets"


@pytest.mark.django_db
def test_name_change_does_not_change_existing_slug() -> None:
    tag = Tag.objects.create(name="Gift Sets")
    original_slug = tag.slug
    tag.name = "Renamed"
    tag.save()
    assert tag.slug == original_slug


@pytest.mark.django_db
def test_str_returns_name() -> None:
    tag = Tag.objects.create(name="Gift Sets")
    assert str(tag) == "Gift Sets"


@pytest.mark.django_db
def test_product_can_have_multiple_tags() -> None:
    from catalog.factories import ProductFactory

    product = ProductFactory()
    tag_one = TagFactory()
    tag_two = TagFactory()
    product.tags.add(tag_one, tag_two)
    assert set(product.tags.all()) == {tag_one, tag_two}
