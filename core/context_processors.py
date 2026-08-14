"""Generic, project-wide context processors.

``store.context_processors.store_settings`` stays in ``store/`` since it's
about that app's own singleton; this module is for processors that aren't
about any one app's data.
"""

from __future__ import annotations

from django.http import HttpRequest


def canonical_url(request: HttpRequest) -> dict[str, str]:
    """§34's canonical URL, computed once, everywhere — deliberately
    strips the query string (``request.path``, not
    ``request.get_full_path()``): a filtered listing page
    (``?category=x&sort=y``) canonicalizes to its own unfiltered URL, not
    to itself, so search engines don't index every filter combination as
    a separate page.
    """
    return {"canonical_url": request.build_absolute_uri(request.path)}
