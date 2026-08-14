"""Media storage backends.

Which backend is active is decided entirely by which settings module is
loaded (``dev.py`` sets ``STORAGES["default"]`` to Django's built-in
``FileSystemStorage``; ``prod.py`` sets it to :class:`R2MediaStorage` below).
Nothing in application code branches on ``settings.DEBUG`` to pick a backend.
"""

from __future__ import annotations

from typing import ClassVar

from storages.backends.s3boto3 import S3Boto3Storage


class R2MediaStorage(S3Boto3Storage):  # type: ignore[misc]  # django-storages ships no stubs
    """Cloudflare R2 (S3-compatible API) storage for user-uploaded media.

    ``object_parameters`` sets ``Cache-Control`` on every object at
    upload time (§36: "aggressive HTTP caching on static assets and
    images", roadmap Stage 12) — safe to cache for a full year because
    every URL under this storage is immutable in practice:
    ``file_overwrite = False`` means a same-named upload never replaces
    bytes at an existing URL, and ``ProductImage.save()`` (catalog/
    models.py) only ever regenerates a derivative when the *source* image
    actually changed, producing a new file (and therefore a new URL) each
    time. The static half of this same deliverable (CSS/JS/fonts) is
    Stage 13's job — Caddy, not Django, will serve those in production,
    and no Caddyfile exists yet to set headers on; see specs/state.md.
    """

    file_overwrite = False
    default_acl = None
    object_parameters: ClassVar[dict[str, str]] = {"CacheControl": "max-age=31536000, immutable"}
