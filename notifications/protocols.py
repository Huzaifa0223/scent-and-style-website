"""``NotificationChannel`` protocol (requirements §26). WhatsApp is the
only MVP implementation (``whatsapp.channel.WhatsAppLinkChannel``); SMS,
email, push, and the WhatsApp Business API are later implementations of
this same protocol, per §26 — nothing outside ``notifications/`` may
assume WhatsApp is how a message actually gets delivered.
"""

from __future__ import annotations

from typing import Protocol


class NotificationChannel(Protocol):
    def build_url(self, *, phone: str, message: str) -> str: ...
