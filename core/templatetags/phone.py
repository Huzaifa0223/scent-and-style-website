"""Phone-number presentation filters for templates.

Store-managed contact fields are free-form enough to preserve the merchant's
preferred display formatting, but ``tel:`` URIs need a narrower character set.
Centralising that cleanup here keeps templates from inventing their own ad-hoc
string munging and preserves a leading ``+`` for international numbers.
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="tel_target")
def tel_target(value: str | None) -> str:
    """Return a safe ``tel:`` target while preserving E.164's leading ``+``."""
    if not value:
        return ""
    stripped = value.strip()
    prefix = "+" if stripped.startswith("+") else ""
    digits = "".join(character for character in stripped if character.isdigit())
    return f"{prefix}{digits}"
