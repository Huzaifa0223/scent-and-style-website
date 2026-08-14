"""Reusable field validators (§41, roadmap Stage 13)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from core.config import MAX_IMAGE_UPLOAD_BYTES


def validate_image_upload_size(file: UploadedFile[bytes]) -> None:
    """Rejects an uploaded image over ``MAX_IMAGE_UPLOAD_BYTES``.

    Django's ``forms.ImageField`` (auto-derived by every ``ModelForm`` in
    this project that exposes an ``ImageField``) already rejects a
    non-image payload by opening it with Pillow and calling
    ``Image.verify()`` — a real content/magic-byte check, not an
    extension check. This validator adds the one thing that check
    doesn't cover: a hard size cap, so a large-but-genuinely-valid image
    can't be used to exhaust memory or CPU during synchronous derivative
    generation (``core/images.py``).
    """
    if file.size is not None and file.size > MAX_IMAGE_UPLOAD_BYTES:
        max_mb = MAX_IMAGE_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(f"Image must be smaller than {max_mb:.0f} MB.", code="file_too_large")
