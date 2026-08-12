"""Product image upload/replace forms (Stage 3).

Reorder, primary selection, and delete are batch/single-row operations
over existing rows, not per-field validation problems — handled directly
in ``portal/image_views.py`` rather than through a form.
"""

from __future__ import annotations

from catalog.models import ProductImage

from .forms import _StyledModelForm


class ProductImageUploadForm(_StyledModelForm[ProductImage]):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text"]


class ProductImageReplaceForm(_StyledModelForm[ProductImage]):
    """Swaps only the file — position, is_primary, and alt_text are left
    exactly as they were on the existing row."""

    class Meta:
        model = ProductImage
        fields = ["image"]
