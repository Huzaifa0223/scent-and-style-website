"""The project's single currency formatter.

CLAUDE.md: "nothing in the project formats currency inline." Every template
renders a money value through this filter — never an inline f-string or
``{{ value }} Rs.`` — so the thousands separator, decimal places, and symbol
placement change in exactly one place.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

_CURRENCY_SYMBOLS: dict[str, str] = {"PKR": "Rs."}


@register.filter(name="money")
def money(value: Decimal | int | float | str | None, currency_code: str = "PKR") -> str:
    """Format ``value`` as a currency string, e.g. ``Rs. 1,234.00``.

    ``currency_code`` defaults to PKR (the only currency this single-merchant
    store supports) but accepts ``store_settings.currency`` from a template
    so the formatter never hard-codes a merchant-specific value itself.
    """
    try:
        amount = Decimal(str(value)) if value is not None else Decimal("0")
    except InvalidOperation:
        amount = Decimal("0")
    amount = amount.quantize(Decimal("0.01"))
    symbol = _CURRENCY_SYMBOLS.get(currency_code, currency_code)
    return f"{symbol} {amount:,.2f}"
