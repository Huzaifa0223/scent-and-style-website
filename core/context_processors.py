"""Generic, project-wide context processors.

``store.context_processors.store_settings`` stays in ``store/`` since it's
about that app's own singleton; this module is for processors that aren't
about any one app's data.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.http import HttpRequest

_APP_CSS_PATH = settings.BASE_DIR / "static" / "css" / "app.css"


def static_asset_version(request: HttpRequest) -> dict[str, str]:  # noqa: ARG001
    """A cache-busting query param for ``static/css/app.css``.

    ``/static/*`` is served with a one-year ``immutable`` Cache-Control
    header (deploy/Caddyfile) at a fixed URL with no filename hashing
    (STORAGES uses plain StaticFilesStorage — see config/settings/prod.py's
    SERVE_STATIC_FROM_R2 comment on why ManifestStaticFilesStorage-style
    hashing isn't in play here). Without something that changes the URL,
    every visitor who loaded the site before a CSS deploy keeps the old
    stylesheet for a year. The compiled file's own mtime — rewritten by
    every ``tailwindcss ... -o static/css/app.css`` build — is a free,
    already-correct version signal with no extra deploy step to forget.
    """
    try:
        version = str(int(os.path.getmtime(_APP_CSS_PATH)))
    except OSError:
        version = "0"
    return {"static_asset_version": version}


def canonical_url(request: HttpRequest) -> dict[str, str]:
    """§34's canonical URL, computed once, everywhere — deliberately
    strips the query string (``request.path``, not
    ``request.get_full_path()``): a filtered listing page
    (``?category=x&sort=y``) canonicalizes to its own unfiltered URL, not
    to itself, so search engines don't index every filter combination as
    a separate page.
    """
    return {"canonical_url": request.build_absolute_uri(request.path)}
