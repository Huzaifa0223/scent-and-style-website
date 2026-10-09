from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from core.templatetags.phone import tel_target
from notifications.whatsapp.channel import WhatsAppLinkChannel

from .models import StoreSettings


def store_settings(request: HttpRequest) -> dict[str, Any]:
    """Expose store settings and the shared WhatsApp contact link to templates."""
    settings = StoreSettings.load()
    whatsapp_url = ""
    if settings.whatsapp_number:
        whatsapp_url = WhatsAppLinkChannel().build_url(
            phone=tel_target(settings.whatsapp_number),
            message="Hi! I have a question about your products.",
        )
    return {"store_settings": settings, "store_whatsapp_url": whatsapp_url}
