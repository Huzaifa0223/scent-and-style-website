"""Product create/edit views (Stage 3).

The only place ``ProductVariant`` rows are created, edited, or deleted from
the portal — there is no standalone variant-delete endpoint, so deletion
can never bypass ``BaseProductVariantFormSet.clean()``; it only happens as
part of this view's own atomic save.

Not built on Django's ``CreateView``/``UpdateView`` generics: those assume
one form. A product form plus its variant formset needs both validated
together before anything is written, which is simplest as a plain ``View``
with an explicit ``get``/``post``.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.forms import BaseInlineFormSet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import AttributeValue, Product, ProductVariant, VariantAttributeValue

from .image_forms import ProductImageUploadForm
from .product_forms import (
    ProductForm,
    ProductVariantEditFormSet,
    ProductVariantForm,
    ProductVariantFormSet,
)

_VariantFormSet = BaseInlineFormSet[ProductVariant, Product, ProductVariantForm]


class _ProductFormsetView(PortalPermissionRequiredMixin, View):
    """Shared GET/POST orchestration. Subclasses set ``formset_class`` and
    ``permission_required``, and override ``get_object()``.
    """

    template_name = "portal/product_form.html"
    success_url = reverse_lazy("portal:product_list")
    formset_class: type[_VariantFormSet] = ProductVariantFormSet

    def get_object(self) -> Product | None:
        raise NotImplementedError

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        product = self.get_object()
        form = ProductForm(instance=product)
        formset = self._build_formset(product)
        return self._render(product, form, formset)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        product = self.get_object()
        form = ProductForm(request.POST, instance=product)
        formset = self._build_formset(product, request.POST)

        if form.is_valid() and formset.is_valid():
            return self._save(form, formset)
        return self._render(product, form, formset)

    def _build_formset(
        self, product: Product | None, data: QueryDict | None = None
    ) -> _VariantFormSet:
        # Every existing variant's attribute_values field reads
        # variant_attribute_values.all() (see ProductVariantForm.__init__)
        # — prefetching here is what makes that a cache hit instead of one
        # query per variant on the edit page (roadmap Stage 3's named trap).
        queryset = ProductVariant.objects.prefetch_related("variant_attribute_values")
        return self.formset_class(data, instance=product, queryset=queryset)

    def _render(
        self, product: Product | None, form: ProductForm, formset: _VariantFormSet
    ) -> HttpResponse:
        context: dict[str, Any] = {"object": product, "form": form, "formset": formset}
        if product is not None:
            # prefetch_related("variants") is what keeps each image row's
            # "hero image for: ..." note (ProductVariant.image's reverse
            # accessor) from costing one query per image — the same N+1
            # shape the variant formset had, caught by a query-count test
            # before this view existed rather than after.
            context["images"] = product.images.prefetch_related("variants")
            context["image_upload_form"] = ProductImageUploadForm()
        return render(self.request, self.template_name, context)

    def _save(self, form: ProductForm, formset: _VariantFormSet) -> HttpResponseRedirect:
        """One transaction for the whole edit: product, every surviving
        variant, its attribute-value sync, and every deletion. The two
        deferred constraint triggers (default-variant, attribute-signature
        uniqueness — catalog/migrations/0003, 0004) only check at COMMIT,
        which is what makes it safe to save variants in formset order
        rather than an invariant-satisfying order, and a partial failure
        here must not leave the product half-edited.

        Survivors are saved *before* deletions. That order matters:
        ProductVariant.delete()'s own default-promotion only fires when no
        other variant already holds ``is_default=True`` — saving survivors
        first means a clean()-assigned new default is already in place by
        the time an old default variant is deleted, so that promotion
        correctly no-ops instead of racing it.
        """
        with transaction.atomic():
            product = form.save()

            deleted_forms = set(formset.deleted_forms)
            for variant_form in formset.forms:
                if variant_form in deleted_forms or not variant_form.cleaned_data:
                    continue
                variant = variant_form.save(commit=False)
                variant.product = product
                variant.save()
                self._sync_attribute_values(
                    variant, variant_form.cleaned_data.get("attribute_values") or []
                )

            for variant_form in formset.deleted_forms:
                if variant_form.instance.pk is not None:
                    variant_form.instance.delete()

        return redirect(self.success_url)

    @staticmethod
    def _sync_attribute_values(variant: ProductVariant, values: list[AttributeValue]) -> None:
        desired_ids = {value.pk for value in values}
        existing = {
            vav.value_id: vav for vav in VariantAttributeValue.objects.filter(variant=variant)
        }
        for value_id, existing_vav in existing.items():
            if value_id not in desired_ids:
                existing_vav.delete()
        for value in values:
            if value.pk not in existing:
                VariantAttributeValue.objects.create(variant=variant, value=value)


class ProductCreateView(_ProductFormsetView):
    formset_class = ProductVariantFormSet
    permission_required = ("catalog.add_product",)

    def get_object(self) -> Product | None:
        return None


class ProductUpdateView(_ProductFormsetView):
    formset_class = ProductVariantEditFormSet
    permission_required = ("catalog.change_product",)

    def get_object(self) -> Product:
        return get_object_or_404(Product, pk=self.kwargs["pk"])
