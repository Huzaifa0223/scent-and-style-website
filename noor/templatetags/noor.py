"""Links into the Noor web app, so no template hard-codes its origin."""

from __future__ import annotations

from urllib.parse import quote

from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def noor_links_enabled() -> bool:
    """Whether the storefront shows links into the Noor web app at all.

    ``settings.NOOR_PUBLIC_LINKS`` is off by default so the buttons never
    ship pointing at a site that is not up yet. It gates *only* these links:
    the ``/api/noor/`` and ``/api/kiosk/sync/`` endpoints do not read it.
    """
    return bool(getattr(settings, "NOOR_PUBLIC_LINKS", False))


@register.simple_tag
def noor_ask_url() -> str:
    """The consultant's landing screen."""
    return f"{settings.NOOR_ORIGIN}/#/noor"


@register.simple_tag
def noor_similar_url(slug: str) -> str:
    """\"Find similar\" for one product, keyed by its storefront slug."""
    return f"{settings.NOOR_ORIGIN}/#/p/{quote(slug, safe='')}"
