from __future__ import annotations

from django.urls import URLPattern, path

from . import product_views, taxonomy_views, views

app_name = "portal"

urlpatterns: list[URLPattern] = [
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/create/", product_views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", product_views.ProductUpdateView.as_view(), name="product_edit"),
    path("categories/", taxonomy_views.CategoryListView.as_view(), name="category_list"),
    path("categories/create/", taxonomy_views.CategoryCreateView.as_view(), name="category_create"),
    path(
        "categories/<int:pk>/edit/",
        taxonomy_views.CategoryUpdateView.as_view(),
        name="category_edit",
    ),
    path("brands/", taxonomy_views.BrandListView.as_view(), name="brand_list"),
    path("brands/create/", taxonomy_views.BrandCreateView.as_view(), name="brand_create"),
    path("brands/<int:pk>/edit/", taxonomy_views.BrandUpdateView.as_view(), name="brand_edit"),
    path(
        "attributes/", taxonomy_views.AttributeDefinitionListView.as_view(), name="attribute_list"
    ),
    path(
        "attributes/create/",
        taxonomy_views.AttributeDefinitionCreateView.as_view(),
        name="attribute_create",
    ),
    path(
        "attributes/<int:pk>/edit/",
        taxonomy_views.AttributeDefinitionUpdateView.as_view(),
        name="attribute_edit",
    ),
    path(
        "attributes/<int:pk>/values/add/",
        taxonomy_views.AttributeValueCreateView.as_view(),
        name="attribute_value_create",
    ),
    path(
        "attributes/<int:pk>/values/<int:value_pk>/delete/",
        taxonomy_views.AttributeValueDeleteView.as_view(),
        name="attribute_value_delete",
    ),
]
