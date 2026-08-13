"""``WhatsAppLinkChannel`` — the sole MVP ``NotificationChannel``
implementation (§26). Never sends anything itself: it only builds a
``wa.me`` link that pre-fills a message in *someone's own* WhatsApp
client, for a human (customer at checkout, merchant from an order) to
review and send. There is no WhatsApp API call anywhere in this project.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class WhatsAppLinkChannel:
    def build_url(self, *, phone: str, message: str) -> str:
        """``phone`` is E.164 (``+923...``) or blank. ``wa.me`` wants
        digits only, no leading ``+`` — stripped here, the one place that
        needs to know that. A blank ``phone`` degrades gracefully to
        ``wa.me/?text=...``, a documented WhatsApp behaviour that opens
        the message ready to send to any contact the person picks,
        rather than producing a broken link when a merchant hasn't
        configured `StoreSettings.whatsapp_number` yet.
        """
        digits = phone.lstrip("+")
        return f"https://wa.me/{digits}?text={quote(message)}"
