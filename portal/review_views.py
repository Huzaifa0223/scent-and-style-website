"""Merchant moderation for verified product reviews."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBase, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, View

from accounts.mixins import PortalPermissionRequiredMixin
from orders.models import ProductReview


class ProductReviewListView(PortalPermissionRequiredMixin, ListView[ProductReview]):
    model = ProductReview
    template_name = "portal/review_list.html"
    context_object_name = "reviews"
    permission_required = ("orders.view_productreview",)

    def get_queryset(self) -> QuerySet[ProductReview]:
        if not settings.PRODUCT_REVIEWS_ENABLED:
            raise Http404
        return ProductReview.objects.select_related("product", "order_item__order").order_by(
            "is_approved", "-created_at"
        )


class ProductReviewModerationView(PortalPermissionRequiredMixin, View):
    permission_required = ("orders.change_productreview",)

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if not settings.PRODUCT_REVIEWS_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        review = get_object_or_404(ProductReview, pk=pk)
        approved = request.POST.get("action") == "approve"
        if request.POST.get("action") not in {"approve", "hide"}:
            return HttpResponse("Invalid moderation action.", status=400)
        review.is_approved = approved
        review.save(update_fields=["is_approved", "updated_at"])
        return HttpResponseRedirect(redirect("portal:review_list").url)
