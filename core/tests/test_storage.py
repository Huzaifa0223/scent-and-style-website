from __future__ import annotations

from storages.backends.s3boto3 import S3Boto3Storage

from core.storage import R2MediaStorage, R2StaticStorage


def test_r2_media_storage_is_s3_boto3_storage_subclass() -> None:
    assert issubclass(R2MediaStorage, S3Boto3Storage)


def test_r2_media_storage_does_not_silently_overwrite_files() -> None:
    assert R2MediaStorage.file_overwrite is False


def test_r2_media_storage_sets_a_long_lived_cache_control_header() -> None:
    """§36: "aggressive HTTP caching... on images" — safe at a full year
    because file_overwrite=False and ProductImage.save() only ever
    produces a new file (never rewrites an existing URL's bytes)."""
    assert R2MediaStorage.object_parameters == {"CacheControl": "max-age=31536000, immutable"}


def test_r2_static_storage_is_s3_boto3_storage_subclass() -> None:
    assert issubclass(R2StaticStorage, S3Boto3Storage)


def test_r2_static_storage_overwrites_because_collectstatic_reuses_keys() -> None:
    """The opposite of the media backend, deliberately. collectstatic writes
    the same object keys on every deploy, so refusing to overwrite would
    leave the site serving the previous release's assets forever."""
    assert R2StaticStorage.file_overwrite is True


def test_r2_static_storage_does_not_claim_assets_are_immutable() -> None:
    """The media backend's year-long immutable cache would be actively wrong
    here: static filenames are not content-hashed, so app.css keeps its URL
    across releases. Caching it as immutable would strand visitors on a
    stale stylesheet with no way to recover short of a hard refresh."""
    cache_control = R2StaticStorage.object_parameters["CacheControl"]

    assert "immutable" not in cache_control
    assert "must-revalidate" in cache_control


def test_the_two_backends_write_to_separate_prefixes() -> None:
    """Static and media share one R2 bucket; only the prefix keeps a
    collected asset from landing on top of an uploaded product image."""
    assert R2StaticStorage.location == "static"
    assert getattr(R2MediaStorage, "location", "") != R2StaticStorage.location
