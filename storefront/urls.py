from __future__ import annotations

from django.urls import URLPattern, path

from storefront.views import HomeView, ProductDetailView, ProductListView

app_name = "storefront"

urlpatterns: list[URLPattern] = [
    path("", HomeView.as_view(), name="home"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("category/<slug:category_slug>/", ProductListView.as_view(), name="category_product_list"),
    path("product/<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
