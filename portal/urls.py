from __future__ import annotations

from django.urls import URLPattern, path
from django.views.generic import RedirectView

from . import (
    image_views,
    inventory_views,
    order_views,
    product_actions,
    product_views,
    taxonomy_views,
    views,
)

app_name = "portal"

urlpatterns: list[URLPattern] = [
    path("", RedirectView.as_view(url="/admin-portal/products/"), name="portal_index"),
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/create/", product_views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/edit/", product_views.ProductUpdateView.as_view(), name="product_edit"),
    path(
        "products/<int:pk>/publish/",
        product_actions.ProductPublishView.as_view(),
        name="product_publish",
    ),
    path(
        "products/<int:pk>/unpublish/",
        product_actions.ProductUnpublishView.as_view(),
        name="product_unpublish",
    ),
    path(
        "products/<int:pk>/archive/",
        product_actions.ProductArchiveView.as_view(),
        name="product_archive",
    ),
    path(
        "products/<int:pk>/feature/",
        product_actions.ProductFeatureView.as_view(),
        name="product_feature",
    ),
    path(
        "products/<int:pk>/unfeature/",
        product_actions.ProductUnfeatureView.as_view(),
        name="product_unfeature",
    ),
    path(
        "products/<int:pk>/images/upload/",
        image_views.ProductImageUploadView.as_view(),
        name="product_image_upload",
    ),
    path(
        "products/<int:pk>/images/reorder/",
        image_views.ProductImageReorderView.as_view(),
        name="product_image_reorder",
    ),
    path(
        "products/<int:pk>/images/<int:image_pk>/delete/",
        image_views.ProductImageDeleteView.as_view(),
        name="product_image_delete",
    ),
    path(
        "products/<int:pk>/images/<int:image_pk>/replace/",
        image_views.ProductImageReplaceView.as_view(),
        name="product_image_replace",
    ),
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
    path("inventory/", inventory_views.InventoryListView.as_view(), name="inventory_list"),
    path(
        "inventory/<int:pk>/adjust/",
        inventory_views.InventoryAdjustView.as_view(),
        name="inventory_adjust",
    ),
    path("orders/", order_views.OrderListView.as_view(), name="order_list"),
    path("orders/<int:pk>/", order_views.OrderDetailView.as_view(), name="order_detail"),
    path(
        "orders/<int:pk>/status/",
        order_views.OrderStatusTransitionView.as_view(),
        name="order_status_transition",
    ),
    path(
        "orders/<int:pk>/tracking/",
        order_views.OrderTrackingUpdateView.as_view(),
        name="order_tracking_update",
    ),
    path(
        "orders/<int:pk>/lines/add/",
        order_views.OrderLineAddView.as_view(),
        name="order_line_add",
    ),
    path(
        "orders/<int:pk>/lines/<int:item_pk>/quantity/",
        order_views.OrderLineQuantityView.as_view(),
        name="order_line_quantity",
    ),
    path(
        "orders/<int:pk>/lines/<int:item_pk>/price/",
        order_views.OrderLinePriceView.as_view(),
        name="order_line_price",
    ),
    path(
        "orders/<int:pk>/lines/<int:item_pk>/remove/",
        order_views.OrderLineRemoveView.as_view(),
        name="order_line_remove",
    ),
]
