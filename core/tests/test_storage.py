from __future__ import annotations

from storages.backends.s3boto3 import S3Boto3Storage

from core.storage import R2MediaStorage


def test_r2_media_storage_is_s3_boto3_storage_subclass() -> None:
    assert issubclass(R2MediaStorage, S3Boto3Storage)


def test_r2_media_storage_does_not_silently_overwrite_files() -> None:
    assert R2MediaStorage.file_overwrite is False


def test_r2_media_storage_sets_a_long_lived_cache_control_header() -> None:
    """§36: "aggressive HTTP caching... on images" — safe at a full year
    because file_overwrite=False and ProductImage.save() only ever
    produces a new file (never rewrites an existing URL's bytes)."""
    assert R2MediaStorage.object_parameters == {"CacheControl": "max-age=31536000, immutable"}
