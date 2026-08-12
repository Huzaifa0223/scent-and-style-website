"""Synchronous image derivative generation (§2.5).

Synchronous is a deliberate MVP choice, not an oversight — a merchant
uploading a handful of images tolerates a two-second save; a broker and
worker process to avoid that cost doesn't pay for itself yet. Logged as debt
in TODO.md if bulk import (Stage 16) ever makes it painful.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import IO

from django.core.files.base import ContentFile
from PIL import Image

from core.config import IMAGE_DERIVATIVE_QUALITY


@dataclass(frozen=True)
class ImageDerivativeSpec:
    name: str
    max_dimension: int


DERIVATIVE_SPECS: tuple[ImageDerivativeSpec, ...] = (
    ImageDerivativeSpec("thumb", 200),
    ImageDerivativeSpec("card", 600),
    ImageDerivativeSpec("full", 1400),
)


def resize_and_encode(source_file: IO[bytes], max_dimension: int, fmt: str) -> ContentFile[bytes]:
    """Resize ``source_file`` so its longest edge is ``max_dimension`` px
    (never upscaling smaller sources), preserving aspect ratio, and encode
    as ``fmt`` (``"WEBP"`` or ``"JPEG"``).
    """
    source_file.seek(0)
    image = Image.open(source_file)
    image = image.convert("RGB")
    image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=IMAGE_DERIVATIVE_QUALITY)
    buffer.seek(0)

    ext = "webp" if fmt == "WEBP" else "jpg"
    return ContentFile(buffer.read(), name=f"derivative.{ext}")
