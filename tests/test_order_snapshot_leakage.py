"""Roadmap Stage 8 gate 2, automated: "grep the order templates for
`.variant.price` and `.variant.product.name` — both must return nothing."
Every value an order-rendering template shows must come from OrderItem's
own snapshot fields, never re-read live through `.variant`.

`checkout.html` is deliberately excluded — it renders the *cart's* line
items (pre-order review, via cart.services.CartLine, whose `.variant` is
a live ProductVariant by design, not an OrderItem snapshot), so the same
substring pattern there is legitimate and would be a false positive here.
Every other template under templates/orders/ renders Order/OrderItem data
and is checked; a future Stage 10 portal order-detail template lands
under the same directory and is covered automatically.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORDERS_TEMPLATES_DIR = PROJECT_ROOT / "templates" / "orders"
EXCLUDED_TEMPLATES = {"checkout.html"}
FORBIDDEN_PATTERNS = [".variant.price", ".variant.product.name"]


def test_no_order_template_reads_price_or_product_name_through_the_variant_fk() -> None:
    offenders: list[str] = []
    for path in ORDERS_TEMPLATES_DIR.glob("*.html"):
        if path.name in EXCLUDED_TEMPLATES:
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                offenders.append(f"{path.name}: {pattern}")
    assert offenders == [], f"snapshot leakage in order templates: {offenders}"
