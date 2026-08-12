"""Media storage backends.

Which backend is active is decided entirely by which settings module is
loaded (``dev.py`` sets ``STORAGES["default"]`` to Django's built-in
``FileSystemStorage``; ``prod.py`` sets it to :class:`R2MediaStorage` below).
Nothing in application code branches on ``settings.DEBUG`` to pick a backend.
"""

from __future__ import annotations

from storages.backends.s3boto3 import S3Boto3Storage


class R2MediaStorage(S3Boto3Storage):  # type: ignore[misc]  # django-storages ships no stubs
    """Cloudflare R2 (S3-compatible API) storage for user-uploaded media."""

    file_overwrite = False
    default_acl = None
