"""ModelForms for the merchant portal's simple CRUD surfaces.

Product's own form (with its variant inline formset) lives in
``portal/product_forms.py`` — the formset logic is substantial enough to
warrant its own module rather than crowding this one.

Store settings has no form here — ``/django-admin/`` is that surface for
now (Stage 1 log; Stage 17 builds the portal-native replacement).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar, cast

from django import forms
from django.db.models import Model

from catalog.models import AttributeDefinition, AttributeValue, Brand, Category
from core.forms import AriaDescribedByMixin, StyledFieldMixin

_M = TypeVar("_M", bound=Model)


class _StyledModelForm(AriaDescribedByMixin, StyledFieldMixin, forms.ModelForm[_M], Generic[_M]):
    """Generic over the model, like ``catalog.models.ProductQuerySet`` is
    over ``Product`` — each concrete form below binds its own
    (``CategoryForm`` is ``_StyledModelForm[Category]`` via its
    ``Meta.model``), so ``form.save()`` keeps returning the specific
    model, not the base one. Styling and aria wiring both come from
    ``core.forms`` mixins now — neither is reimplemented here.
    """


class CategoryForm(_StyledModelForm[Category]):
    class Meta:
        model = Category
        fields = [
            "name",
            "parent",
            "description",
            "image",
            "position",
            "is_published",
            "meta_title",
            "meta_description",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Only top-level categories may be a parent (Category.clean() rejects
        # a three-level chain at save time; excluding subcategories here
        # gives the merchant that feedback before they submit, not after).
        parent_field = cast("forms.ModelChoiceField[Category]", self.fields["parent"])
        parent_field.queryset = Category.objects.filter(parent__isnull=True)


class BrandForm(_StyledModelForm[Brand]):
    class Meta:
        model = Brand
        fields = ["name", "logo", "is_published"]


class AttributeDefinitionForm(_StyledModelForm[AttributeDefinition]):
    class Meta:
        model = AttributeDefinition
        fields = ["name", "is_filterable", "is_variant_option", "position"]


class AttributeValueForm(_StyledModelForm[AttributeValue]):
    class Meta:
        model = AttributeValue
        fields = ["value", "position"]
