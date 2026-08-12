"""Category, Brand, and Attribute (definition + value) CRUD — the catalog's
supporting vocabulary, as opposed to products themselves (portal/views.py).
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import AttributeDefinition, AttributeValue, Brand, Category

from .forms import AttributeDefinitionForm, AttributeValueForm, BrandForm, CategoryForm


class CategoryListView(PortalPermissionRequiredMixin, ListView[Category]):
    model = Category
    template_name = "portal/category_list.html"
    context_object_name = "categories"
    permission_required = ("catalog.view_category",)

    def get_queryset(self) -> QuerySet[Category]:
        return Category.objects.select_related("parent").order_by("position", "name")


class CategoryCreateView(PortalPermissionRequiredMixin, CreateView[Category, CategoryForm]):
    model = Category
    form_class = CategoryForm
    template_name = "portal/category_form.html"
    success_url = reverse_lazy("portal:category_list")
    permission_required = ("catalog.add_category",)


class CategoryUpdateView(PortalPermissionRequiredMixin, UpdateView[Category, CategoryForm]):
    model = Category
    form_class = CategoryForm
    template_name = "portal/category_form.html"
    success_url = reverse_lazy("portal:category_list")
    permission_required = ("catalog.change_category",)


class BrandListView(PortalPermissionRequiredMixin, ListView[Brand]):
    model = Brand
    template_name = "portal/brand_list.html"
    context_object_name = "brands"
    permission_required = ("catalog.view_brand",)


class BrandCreateView(PortalPermissionRequiredMixin, CreateView[Brand, BrandForm]):
    model = Brand
    form_class = BrandForm
    template_name = "portal/brand_form.html"
    success_url = reverse_lazy("portal:brand_list")
    permission_required = ("catalog.add_brand",)


class BrandUpdateView(PortalPermissionRequiredMixin, UpdateView[Brand, BrandForm]):
    model = Brand
    form_class = BrandForm
    template_name = "portal/brand_form.html"
    success_url = reverse_lazy("portal:brand_list")
    permission_required = ("catalog.change_brand",)


class AttributeDefinitionListView(PortalPermissionRequiredMixin, ListView[AttributeDefinition]):
    model = AttributeDefinition
    template_name = "portal/attribute_list.html"
    context_object_name = "attribute_definitions"
    permission_required = ("catalog.view_attributedefinition",)

    def get_queryset(self) -> QuerySet[AttributeDefinition]:
        return AttributeDefinition.objects.prefetch_related("values").order_by("position", "name")


class AttributeDefinitionCreateView(
    PortalPermissionRequiredMixin, CreateView[AttributeDefinition, AttributeDefinitionForm]
):
    model = AttributeDefinition
    form_class = AttributeDefinitionForm
    template_name = "portal/attribute_form.html"
    success_url = reverse_lazy("portal:attribute_list")
    permission_required = ("catalog.add_attributedefinition",)


class AttributeDefinitionUpdateView(
    PortalPermissionRequiredMixin, UpdateView[AttributeDefinition, AttributeDefinitionForm]
):
    model = AttributeDefinition
    form_class = AttributeDefinitionForm
    template_name = "portal/attribute_form.html"
    success_url = reverse_lazy("portal:attribute_list")
    permission_required = ("catalog.change_attributedefinition",)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["values"] = self.object.values.order_by("position", "value")
        context["value_form"] = AttributeValueForm()
        return context


class AttributeValueCreateView(PortalPermissionRequiredMixin, View):
    """POST-only — adds one value to a definition and redirects back to
    that definition's edit page. Not a full CreateView because there's
    nothing to render on its own; it only ever appears nested inside
    AttributeDefinitionUpdateView's page."""

    permission_required = ("catalog.add_attributevalue",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        definition = get_object_or_404(AttributeDefinition, pk=pk)
        form = AttributeValueForm(request.POST)
        if form.is_valid():
            value = form.save(commit=False)
            value.definition = definition
            value.save()
        return redirect("portal:attribute_edit", pk=definition.pk)


class AttributeValueDeleteView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.delete_attributevalue",)

    def post(self, request: HttpRequest, pk: int, value_pk: int) -> HttpResponseRedirect:
        value = get_object_or_404(AttributeValue, pk=value_pk, definition_id=pk)
        value.delete()
        return redirect("portal:attribute_edit", pk=pk)
