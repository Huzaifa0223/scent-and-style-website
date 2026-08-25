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
    """Return a safe ``tel:`` target while preserving a leading ``+``.

    ``StoreSettings`` contact fields intentionally keep merchant-entered
    display formatting, so template code still needs a URI-safe variant for
    ``tel:`` links. This filter strips everything except digits plus one
    leading ``+``; full number validation remains the form/model layer's job,
    because this filter may also be used with already-saved historical values.
    """
    if not value:
        return ""
    stripped = value.strip()
    prefix = "+" if stripped.startswith("+") else ""
    digits = "".join(character for character in stripped if character.isdigit())
    return f"{prefix}{digits}"
