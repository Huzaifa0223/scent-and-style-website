"""Product image management views (Stage 3).

Three endpoints, deliberately not one: upload needs ``add_productimage``,
reorder/re-primary needs ``change_productimage``, delete needs
``delete_productimage`` — the seeded "Staff" group has the first two but
not the third (accounts/migrations/0001), and bundling delete into the
same view as reorder would silently loosen that boundary. Unlike the
variant formset, there's no "at least one image" invariant to protect
(``test_deleting_the_only_image_leaves_zero_images_without_error``,
Stage 2), so a standalone per-image delete endpoint bypasses no
cross-row validation — it's a different situation from variants, not an
inconsistent one.
"""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import Product, ProductImage, ProductVariant

from .image_forms import ProductImageReplaceForm, ProductImageUploadForm


def _parse_ids(values: list[str]) -> list[int]:
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(value))
        except ValueError:
            continue
    return parsed


class ProductImageUploadView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.add_productimage",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)
        form = ProductImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.product = product
            image.save()
        else:
            messages.error(request, "Couldn't add that image — check the file and try again.")
        return redirect("portal:product_edit", pk=product.pk)


class ProductImageReorderView(PortalPermissionRequiredMixin, View):
    """Position updates and an optional primary reassignment, in one
    transaction. The one-primary-image invariant is a deferred constraint
    trigger (catalog/migrations/0005) specifically so this doesn't have to
    get every statement's order exactly right to be safe — it still is
    (old primary unset before the new one is set), but the deferred check
    is the backstop, not a formality.
    """

    permission_required = ("catalog.change_productimage",)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        product = get_object_or_404(Product, pk=pk)
        images = {image.pk: image for image in product.images.all()}

        order = _parse_ids(request.POST.getlist("order"))
        if any(image_id not in images for image_id in order):
            return HttpResponseBadRequest(
                "Reorder request referenced an image that isn't on this product."
            )

        primary_raw = request.POST.get("primary_image", "").strip()
        primary_id = int(primary_raw) if primary_raw.isdigit() else None
        if primary_id is not None and primary_id not in images:
            return HttpResponseBadRequest(
                "Primary-image selection referenced an image that isn't on this product."
            )

        # `order` may not list every image (a stale page, a partial submit)
        # — apply the submitted order first, then append anything missing
        # after, in its existing relative order (dict preserves the
        # position-ordered iteration from the queryset above). Enumerating
        # over `order` alone would leave an omitted image on its old
        # position, colliding with whatever was just reassigned there.
        remaining = [image_id for image_id in images if image_id not in set(order)]
        full_order = order + remaining

        with transaction.atomic():
            for position, image_id in enumerate(full_order):
                image = images[image_id]
                if image.position != position:
                    image.position = position
                    image.save(update_fields=["position", "updated_at"])

            if primary_id is not None:
                new_primary = images[primary_id]
                if not new_primary.is_primary:
                    for image in images.values():
                        if image.is_primary and image.pk != primary_id:
                            image.is_primary = False
                            image.save(update_fields=["is_primary", "updated_at"])
                    new_primary.is_primary = True
                    new_primary.save(update_fields=["is_primary", "updated_at"])

        return redirect("portal:product_edit", pk=product.pk)


class ProductImageDeleteView(PortalPermissionRequiredMixin, View):
    """Deleting an image a variant uses as its hero image nulls that FK
    (ProductVariant.image is SET_NULL) — that's a DB-level guarantee
    (catalog/tests/test_product_image.py), not something this view has to
    implement. What this view adds on top: telling the merchant which
    variants that just happened to, rather than it happening silently.
    """

    permission_required = ("catalog.delete_productimage",)

    def post(self, request: HttpRequest, pk: int, image_pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)
        image = get_object_or_404(ProductImage, pk=image_pk, product=product)

        affected_skus = list(
            ProductVariant.objects.filter(image=image).values_list("sku", flat=True)
        )
        image.delete()

        if affected_skus:
            messages.warning(
                request,
                "Removed as the hero image for: " + ", ".join(sorted(affected_skus)) + ".",
            )

        return redirect("portal:product_edit", pk=product.pk)


class ProductImageReplaceView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.change_productimage",)

    def post(self, request: HttpRequest, pk: int, image_pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)
        image = get_object_or_404(ProductImage, pk=image_pk, product=product)
        form = ProductImageReplaceForm(request.POST, request.FILES, instance=image)
        if form.is_valid():
            form.save()
        else:
            messages.error(request, "Couldn't replace that image — check the file and try again.")
        return redirect("portal:product_edit", pk=product.pk)
