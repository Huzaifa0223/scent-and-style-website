from __future__ import annotations

from storages.backends.s3boto3 import S3Boto3Storage

from core.storage import R2MediaStorage


def test_r2_media_storage_is_s3_boto3_storage_subclass() -> None:
    assert issubclass(R2MediaStorage, S3Boto3Storage)


def test_r2_media_storage_does_not_silently_overwrite_files() -> None:
    assert R2MediaStorage.file_overwrite is False
