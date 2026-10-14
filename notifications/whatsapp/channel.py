"""``WhatsAppLinkChannel`` — the sole MVP ``NotificationChannel``
implementation (§26). Never sends anything itself: it only builds a
``wa.me`` link that pre-fills a message in *someone's own* WhatsApp
client, for a human (customer at checkout, merchant from an order) to
review and send. There is no WhatsApp API call anywhere in this project.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from core.phone import normalize_pk_mobile


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
        # Merchants type the number the way they say it ("0334 1172222"),
        # but wa.me needs the country code and no leading 0. A recognisable
        # Pakistani mobile is converted; anything else is passed through
        # digits-only.
        normalised = normalize_pk_mobile(phone)
        digits = normalised.lstrip("+") if normalised else "".join(c for c in phone if c.isdigit())
        return f"https://wa.me/{digits}?text={quote(message)}"
