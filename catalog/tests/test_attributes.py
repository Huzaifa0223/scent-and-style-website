from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from catalog.factories import AttributeDefinitionFactory, AttributeValueFactory
from catalog.models import AttributeDefinition, AttributeValue


@pytest.mark.django_db
def test_attribute_definition_slug_generated() -> None:
    definition = AttributeDefinition.objects.create(name="Size")
    assert definition.slug == "size"


@pytest.mark.django_db
def test_attribute_value_unique_per_definition_slug() -> None:
    size = AttributeDefinition.objects.create(name="Size")
    colour = AttributeDefinition.objects.create(name="Colour")
    AttributeValue.objects.create(definition=size, value="Red")
    # Same slug ("red"), but a *different* definition — must be allowed.
    other = AttributeValue.objects.create(definition=colour, value="Red")
    assert other.slug == "red"


@pytest.mark.django_db
def test_attribute_value_slug_collision_within_same_definition_gets_suffixed() -> None:
    size = AttributeDefinition.objects.create(name="Size")
    AttributeValue.objects.create(definition=size, value="Red")
    second = AttributeValue.objects.create(definition=size, value="Red")
    assert second.slug == "red-2"


@pytest.mark.django_db
def test_attribute_value_duplicate_definition_and_slug_raises_integrity_error() -> None:
    """§2.2: AttributeValue is unique on (definition, slug) — enforced at
    the database, not just by the collision-avoiding save() logic, since a
    raw insert or race could still produce a duplicate."""
    size = AttributeDefinition.objects.create(name="Size")
    AttributeValue.objects.create(definition=size, value="Red", slug="red")
    with pytest.raises(IntegrityError), transaction.atomic():
        AttributeValue.objects.create(definition=size, value="Red (dup)", slug="red")


@pytest.mark.django_db
def test_factories_produce_valid_rows() -> None:
    definition = AttributeDefinitionFactory()
    value = AttributeValueFactory(definition=definition)
    assert value.definition_id == definition.pk
    assert value.slug
