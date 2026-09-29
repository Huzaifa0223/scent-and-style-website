from __future__ import annotations

from django.urls import URLPattern, path

from storefront.views import (
    BrandListView,
    HomeView,
    ProductDetailView,
    ProductListView,
    ProductReviewSubmitView,
)

app_name = "storefront"

urlpatterns: list[URLPattern] = [
    path("", HomeView.as_view(), name="home"),
    path("brands/", BrandListView.as_view(), name="brand_list"),
    path("products/", ProductListView.as_view(), name="product_list"),
    path("category/<slug:category_slug>/", ProductListView.as_view(), name="category_product_list"),
    path("product/<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
    path(
        "product/<slug:slug>/reviews/",
        ProductReviewSubmitView.as_view(),
        name="product_review_submit",
    ),
]
