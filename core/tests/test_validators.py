"""core/validators.py (§41, roadmap Stage 13)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from core.config import MAX_IMAGE_UPLOAD_BYTES
from core.validators import validate_image_upload_size


def test_validate_image_upload_size_allows_a_file_at_exactly_the_cap() -> None:
    file = SimpleUploadedFile("photo.jpg", b"x" * MAX_IMAGE_UPLOAD_BYTES)

    validate_image_upload_size(file)  # must not raise


def test_validate_image_upload_size_rejects_a_file_one_byte_over_the_cap() -> None:
    file = SimpleUploadedFile("photo.jpg", b"x" * (MAX_IMAGE_UPLOAD_BYTES + 1))

    with pytest.raises(ValidationError):
        validate_image_upload_size(file)


def test_default_storage_strips_path_separators_from_an_uploaded_filename() -> None:
    """§41's "filename sanitiser" — Django's own ``Storage.get_valid_name()``
    (``django.utils.text.get_valid_filename()``), not custom code: no
    path separator survives, so no path-traversal component can either."""
    sanitized = default_storage.get_valid_name("../../etc/passwd")

    assert "/" not in sanitized
    assert "\\" not in sanitized


def test_default_storage_replaces_unsafe_characters_in_an_uploaded_filename() -> None:
    sanitized = default_storage.get_valid_name("my photo <script>.jpg")

    for unsafe_char in (" ", "<", ">"):
        assert unsafe_char not in sanitized
    assert sanitized.endswith(".jpg")
