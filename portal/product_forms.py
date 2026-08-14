"""Product create/edit form and its variant inline formset (Stage 3).

Three cross-form validation concerns (>=1 surviving variant, default-variant
swap/auto-promotion, duplicate attribute-set rejection) plus a custom
non-model field for attribute values are enough to warrant a module of their
own rather than crowding ``portal/forms.py``.

The formset never calls ``save()``. ``BaseModelFormSet.save_existing_objects()``
only saves a form when ``form.has_changed()`` is True — which compares raw
submitted data against initial, not ``cleaned_data`` — so a default that
``clean()`` auto-promotes on an otherwise-untouched form would silently be
skipped. ``portal.product_views`` iterates every surviving form and saves it
unconditionally instead. Deletions go through ``formset.deleted_forms``, not
``formset.deleted_objects`` — the latter is populated by ``save()``, which
this flow never calls; before ``save()`` runs, it doesn't exist.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from catalog.models import AttributeValue, Product, ProductVariant
from core.forms import FIELD_CSS as _FIELD_CSS

from .forms import _StyledModelForm

CREATE_VARIANT_EXTRA_FORMS = 3
"""Blank variant rows shown on the product *create* page. 3 matches
acceptance gate 1's own scenario (three variants across two attributes)
exactly, so a merchant can fill that whole shape without an "add another
row" control, which this pass doesn't build."""

EDIT_VARIANT_EXTRA_FORMS = 1
"""Blank variant rows shown alongside existing ones on the product *edit*
page — one spare row per visit, the same default Django admin's own inline
formsets use; a merchant who needs more saves and reopens."""


class ProductForm(_StyledModelForm[Product]):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "brand",
            "category",
            "subcategory",
            "short_description",
            "description",
            "tags",
            "status",
            "is_featured",
            "meta_title",
            "meta_description",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Only an actual subcategory (has a parent) is a legal choice —
        # Product.clean() enforces "child of the selected category" at
        # save time regardless; this just keeps the dropdown from offering
        # top-level categories that would always fail that check.
        subcategory_field = self.fields["subcategory"]
        assert isinstance(subcategory_field, forms.ModelChoiceField)
        assert subcategory_field.queryset is not None
        subcategory_field.queryset = subcategory_field.queryset.filter(parent__isnull=False)

        # Opt-in (§34: "slug changes are opt-in") — blank on create means
        # "auto-generate from the name" (Product.save()'s own behaviour,
        # unchanged). Changing it on an existing product is exactly the
        # roadmap Stage 12 scenario a redirect must survive:
        # Product.save() records the old value in ProductSlugRedirect
        # itself, so this form doesn't need to know that mechanism exists
        # at all — it only needs to let the merchant submit a new value.
        self.fields["slug"].required = False
        self.fields["slug"].help_text = (
            "Leave blank to auto-generate from the name. Changing the slug on an existing "
            "product keeps the old link working — it 301-redirects to the new one."
        )


class ProductVariantForm(_StyledModelForm[ProductVariant]):
    """``attribute_values`` isn't a model field — ``VariantAttributeValue``
    is a through table, not a direct M2M — so it's declared here and synced
    by the view after save(), the same way any ModelForm field that doesn't
    map onto a model column has to be handled by hand.

    Its ``initial`` is populated from the instance's existing
    ``VariantAttributeValue`` rows below. Without that, editing a product
    would render every variant's attribute checkboxes unchecked, and an
    untouched row would submit an empty set — silently clearing every
    variant's attributes on the next save.
    """

    attribute_values = forms.ModelMultipleChoiceField(
        queryset=AttributeValue.objects.select_related("definition").filter(
            definition__is_variant_option=True
        ),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": _FIELD_CSS, "size": 6}),
    )

    class Meta:
        model = ProductVariant
        fields = [
            "sku",
            "price",
            "compare_at_price",
            "stock_quantity",
            "low_stock_threshold",
            "is_default",
            "is_active",
            "position",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # .all() with no further filtering is the one call that reads a
            # prefetched relation from cache — .values_list() always issues
            # its own fresh query, prefetched or not. The formset passes a
            # prefetch_related("variant_attribute_values") queryset in
            # specifically so this doesn't become an N+1 across variants.
            self.fields["attribute_values"].initial = [
                vav.value_id for vav in self.instance.variant_attribute_values.all()
            ]


class BaseProductVariantFormSet(BaseInlineFormSet[ProductVariant, Product, ProductVariantForm]):
    """Cross-form validation for the three concerns the model's own deferred
    constraint triggers exist to backstop, surfaced here as clean form
    errors instead — a merchant should see "only one variant can be
    default," never a raw IntegrityError.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # A genuine per-instance attribute, not a class attribute merely
        # shadowed by add_fields() — a formset instance is built fresh per
        # request, and this cache must not survive past it.
        self._attribute_value_choices: list[tuple[int, str]] | None = None

    def add_fields(self, form: ProductVariantForm, index: int | None) -> None:
        super().add_fields(form, index)
        # Every form's attribute_values field is deep-copied from the class
        # declaration (BaseForm.__init__ does this for every field), and
        # ModelChoiceIterator re-iterates field.queryset on every render —
        # one query per variant if left alone. Assigning a materialised
        # list of (pk, label) pairs to field.choices bypasses that iterator
        # entirely for rendering, so the underlying query runs once here,
        # not once per form. field.queryset itself is untouched and still
        # does its own (unavoidable, POST-only) validation query.
        if self._attribute_value_choices is None:
            self._attribute_value_choices = [
                (value.pk, str(value))
                for value in AttributeValue.objects.select_related("definition").filter(
                    definition__is_variant_option=True
                )
            ]
        attribute_values_field = form.fields["attribute_values"]
        assert isinstance(attribute_values_field, forms.ModelMultipleChoiceField)
        attribute_values_field.choices = self._attribute_value_choices

    def clean(self) -> None:
        super().clean()
        # clean() runs even when individual forms have errors — bail out
        # before piling cross-form errors on top of a row that's simply
        # incomplete.
        if any(self.errors):
            return

        deleted = set(self.deleted_forms)
        surviving_forms = [form for form in self.forms if form not in deleted and form.cleaned_data]

        if not surviving_forms:
            raise forms.ValidationError(
                "A product must have at least one variant.", code="no_variants"
            )

        signature_owner: dict[tuple[int, ...], forms.BaseForm] = {}
        for form in surviving_forms:
            values = form.cleaned_data.get("attribute_values") or []
            signature = tuple(sorted(value.pk for value in values))
            if not signature:
                continue
            collision = signature_owner.get(signature)
            if collision is not None:
                message = "Another variant already has this exact combination of attributes."
                form.add_error("attribute_values", message)
                collision.add_error("attribute_values", message)
            else:
                signature_owner[signature] = form

        default_forms = [form for form in surviving_forms if form.cleaned_data.get("is_default")]
        if len(default_forms) > 1:
            for form in default_forms:
                form.add_error("is_default", "Only one variant can be the default.")
        elif not default_forms:
            # No survivor explicitly claimed default — promote the first
            # one. Both cleaned_data and instance are set: the view saves
            # every surviving form unconditionally (see module docstring),
            # but setting cleaned_data too keeps this form's own state
            # internally consistent for anything else that reads it.
            promoted = surviving_forms[0]
            promoted.cleaned_data["is_default"] = True
            promoted.instance.is_default = True


ProductVariantFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    form=ProductVariantForm,
    formset=BaseProductVariantFormSet,
    extra=CREATE_VARIANT_EXTRA_FORMS,
    can_delete=True,
)

ProductVariantEditFormSet = inlineformset_factory(
    Product,
    ProductVariant,
    form=ProductVariantForm,
    formset=BaseProductVariantFormSet,
    extra=EDIT_VARIANT_EXTRA_FORMS,
    can_delete=True,
)
