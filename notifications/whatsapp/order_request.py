"""Order on request (D-079): the "ask us to get it for you" WhatsApp link for
a perfume that is off the shelf. Built here, with the other WhatsApp strings,
so nothing outside ``notifications/`` ever constructs a link."""

from __future__ import annotations

from .channel import WhatsAppLinkChannel
from .message_builder import build_order_request_message


def build_order_request_url(
    *,
    whatsapp_number: str,
    product_name: str,
    variant_label: str,
    lead_days: int,
    product_url: str,
) -> str:
    """The wa.me link to the merchant, or ``""`` when no WhatsApp number is
    configured (a request with nobody to receive it must not render).

    The caller passes ``StoreSettings.whatsapp_number`` so a page with many
    variants loads the settings once, not once per variant."""
    if not whatsapp_number:
        return ""
    message = build_order_request_message(
        product_name=product_name,
        variant_label=variant_label,
        lead_days=lead_days,
        product_url=product_url,
    )
    return WhatsAppLinkChannel().build_url(phone=whatsapp_number, message=message)
