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


class R2StaticStorage(S3Boto3Storage):  # type: ignore[misc]  # django-storages ships no stubs
    """Cloudflare R2 storage for collected static assets (CSS/JS/fonts).

    Only used on a platform where nothing else can serve them. The
    documented VPS deployment puts Caddy in front and Caddy serves
    ``STATIC_ROOT`` straight off disk, which is faster and simpler — this
    exists for managed platforms (Railway, Render) where there is no such
    front door and the app process is the only thing listening.

    Selected by ``SERVE_STATIC_FROM_R2`` in ``config/settings/prod.py``,
    never by an ``if DEBUG`` branch, matching :class:`R2MediaStorage`.

    ``file_overwrite`` is True here, unlike the media backend: collectstatic
    re-uploads the same key on every deploy and must replace it. That makes
    the URLs mutable, so the immutable cache directive the media backend
    uses would be wrong — a year-long cache on ``app.css`` would strand
    visitors on a stale stylesheet after a redeploy. ``max-age=3600`` with
    ``must-revalidate`` keeps assets cached without outliving a release.
    A hashed-filename storage would allow the long cache back; that is a
    worthwhile follow-up, not a launch blocker.
    """

    location = "static"
    file_overwrite = True
    default_acl = None
    object_parameters: ClassVar[dict[str, str]] = {"CacheControl": "max-age=3600, must-revalidate"}
