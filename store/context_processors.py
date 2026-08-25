from __future__ import annotations

from django.http import HttpRequest

from notifications.whatsapp.channel import WhatsAppLinkChannel

from .models import StoreSettings


def store_settings(request: HttpRequest) -> dict[str, object]:
    """Expose the singleton StoreSettings row and derived helper values to
    every template render.

    ``whatsapp_contact_url`` is built here — the one place outside
    ``notifications/`` that is allowed to call into ``WhatsAppLinkChannel``
    — so templates never construct WhatsApp deep-link strings directly.
    """
    settings = StoreSettings.load()
    channel = WhatsAppLinkChannel()
    whatsapp_contact_url = channel.build_url(phone=settings.whatsapp_number, message="")
    return {
        "store_settings": settings,
        "whatsapp_contact_url": whatsapp_contact_url,
    }
