from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from . import services


def cart(request: HttpRequest) -> dict[str, Any]:
    """Exposes the current cart's lines/count/subtotal to every template —
    read-only (``services.get_cart()``, never ``get_or_create_cart()``), so
    rendering a page never creates a session or a ``Cart`` row for a
    visitor who hasn't added anything yet."""
    current = services.get_cart(request)
    lines = services.cart_lines(current) if current is not None else []
    return {
        "cart_lines": lines,
        "cart_item_count": sum(line.item.quantity for line in lines),
        "cart_subtotal": services.cart_subtotal(lines),
    }
