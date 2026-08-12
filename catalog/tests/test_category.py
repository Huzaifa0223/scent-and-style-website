from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from catalog.factories import CategoryFactory
from catalog.models import Category


@pytest.mark.django_db
def test_top_level_category_saves_fine() -> None:
    category = Category.objects.create(name="Fragrances")
    assert category.parent is None


@pytest.mark.django_db
def test_subcategory_of_a_top_level_category_saves_fine() -> None:
    top = Category.objects.create(name="Fragrances")
    sub = Category.objects.create(name="Men's Fragrances", parent=top)
    assert sub.parent_id == top.pk


@pytest.mark.django_db
def test_three_level_category_raises_validation_error() -> None:
    """Acceptance gate 3: a category whose parent already has a parent must
    be rejected — only two levels exist."""
    top = Category.objects.create(name="Fragrances")
    sub = Category.objects.create(name="Men's Fragrances", parent=top)
    with pytest.raises(ValidationError) as exc_info:
        Category.objects.create(name="Too Deep", parent=sub)
    assert "parent" in exc_info.value.message_dict


@pytest.mark.django_db
def test_rejected_three_level_category_is_not_persisted() -> None:
    top = Category.objects.create(name="Fragrances")
    sub = Category.objects.create(name="Men's Fragrances", parent=top)
    with pytest.raises(ValidationError):
        Category.objects.create(name="Too Deep", parent=sub)
    assert not Category.objects.filter(name="Too Deep").exists()


@pytest.mark.django_db
def test_slug_generated_and_stable_across_renames() -> None:
    category = Category.objects.create(name="Fragrances")
    original_slug = category.slug
    category.name = "Perfumes"
    category.save()
    assert category.slug == original_slug


@pytest.mark.django_db
def test_factory_produces_a_valid_category() -> None:
    category = CategoryFactory()
    assert category.pk is not None
    assert category.slug
