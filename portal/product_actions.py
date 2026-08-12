"""Product quick-action views: publish, unpublish, feature, unfeature,
archive (roadmap Stage 3).

Five single-field status changes, listed as their own roadmap deliverable
distinct from the product edit form (``portal/product_forms.py`` already
exposes ``status``/``is_featured`` as ordinary edit-form fields) because a
merchant expects to fire these from a product list row without opening the
full form. Same shape as ``portal/image_views.py``: one view per action,
POST-only (no ``get()`` defined, so Django's own ``View.dispatch()``
returns 405 for anything else), each declaring its own
``permission_required`` rather than one endpoint branching on a hidden
"action" field. Unlike the image split, all five resolve to the same
Django permission — ``catalog.change_product`` — because Django's built-in
codenames don't distinguish "publish" from "archive"; both are a change to
an existing ``Product`` row, not a create or delete.

No transition is blocked by current status (publish is idempotent from any
status, including reversing an archive — there is no dedicated "unarchive"
action because publish already covers that transition). Requirements
doesn't specify a product status state machine the way §25 mandates one
for orders, so adding one here would be an invented constraint, not a
spec requirement.

**Archive is a pure status transition, never a cascade.** It sets
``Product.status = ARCHIVED`` and nothing else — no variant is
deactivated, no image is touched, nothing is deleted. Checked before
writing this: no ``cart``, ``orders``, ``inventory``, ``search``, or
``storefront`` app exists yet (roadmap Stages 4/6/7/8), so nothing in this
codebase currently holds a reference to a product by status that archiving
could break. The decision, for those stages to honor once they exist:
storefront browse/search/PDP must filter on ``status=PUBLISHED`` (the same
field the portal list already filters on) to hide archived and draft
products, and archiving must stay non-destructive specifically so that a
future ``OrderItem`` — already specified as an immutable snapshot that
never reads back through the variant FK for display (CLAUDE.md) — keeps
resolving its FK even after the product it snapshotted is archived. A
variant's own ``is_active`` flag is a separate, independent lever a
merchant can still set regardless of the product's status.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View

from accounts.mixins import PortalPermissionRequiredMixin
from catalog.models import Product


class _ProductStatusActionView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.change_product",)
    target_status: str
    success_message: str

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)
        product.status = self.target_status
        product.save(update_fields=["status", "updated_at"])
        messages.success(request, self.success_message.format(name=product.name))
        return redirect("portal:product_list")


class ProductPublishView(_ProductStatusActionView):
    target_status = Product.Status.PUBLISHED
    success_message = '"{name}" is now published.'


class ProductUnpublishView(_ProductStatusActionView):
    target_status = Product.Status.DRAFT
    success_message = '"{name}" moved back to draft.'


class ProductArchiveView(_ProductStatusActionView):
    target_status = Product.Status.ARCHIVED
    success_message = '"{name}" archived.'


class _ProductFeatureActionView(PortalPermissionRequiredMixin, View):
    permission_required = ("catalog.change_product",)
    target_value: bool
    success_message: str

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        product = get_object_or_404(Product, pk=pk)
        product.is_featured = self.target_value
        product.save(update_fields=["is_featured", "updated_at"])
        messages.success(request, self.success_message.format(name=product.name))
        return redirect("portal:product_list")


class ProductFeatureView(_ProductFeatureActionView):
    target_value = True
    success_message = '"{name}" is now featured.'


class ProductUnfeatureView(_ProductFeatureActionView):
    target_value = False
    success_message = '"{name}" is no longer featured.'
