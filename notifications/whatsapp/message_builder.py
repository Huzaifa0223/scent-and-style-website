"""WhatsApp message construction (§21, §26). The *only* place in this
project that builds a WhatsApp message string — CLAUDE.md's own trap note
("nothing outside notifications/ knows WhatsApp exists") applies to
message content exactly as much as to the channel abstraction; an
automated test (``notifications/tests/test_no_inline_construction.py``)
greps every other app for a ``wa.me``/``whatsapp`` string literal.

Every value read from an ``Order`` comes from its own snapshot fields —
``OrderItem.product_name``/``quantity``/``line_total``, never
``.variant.*`` — the same discipline Stage 8 already enforces for order
templates, extended here to WhatsApp text.

**The `WHATSAPP_MESSAGE_MAX_CHARS` budget (`StoreSettings.
whatsapp_message_max_chars`) is an unverified placeholder, not a measured
limit.** §21 is explicit that the real `wa.me` truncation ceiling varies
by browser and WhatsApp client and must be measured empirically on
Android Chrome, iOS Safari, and WhatsApp Web before the default is
finalised — something this agent cannot do. 1000 characters (of raw
message text, before URL-encoding) was chosen as a deliberately
conservative placeholder: comfortably below every publicly-documented
`wa.me` URL-length concern, at the cost of triggering the truncation path
more eagerly than a verified number might need to. See
``docs/whatsapp-limits.md`` and this stage's *Human tasks* entry in
``specs/state.md`` — the measurement is a human task, not a blocker, and
must not be silently marked done by picking a number and moving on.
"""

from __future__ import annotations

from core.templatetags.money import money
from orders.models import Order, OrderItem
from store.models import StoreSettings

# Stage 11 (public order tracking) owns this path. Referencing it now,
# before that view exists, is a deliberate forward reference — same
# pattern as Stage 5's search endpoint existing before Stage 6 wired it
# into a page — not an accident. Until Stage 11 ships, this URL 404s;
# recorded openly in state.md rather than building a stub tracking view
# that would blur Stage 11's own security-sensitive scope (rate limiting,
# phone verification) into this stage.
TRACKING_URL_PATH = "/track/"


def _tracking_url(order: Order) -> str:
    site_url = StoreSettings.load().site_url
    if not site_url:
        return ""
    return f"{site_url.rstrip('/')}{TRACKING_URL_PATH}?order={order.order_number}"


def _item_line(item: OrderItem, index: int) -> str:
    return f"{index}. {item.product_name} x{item.quantity} - {money(item.line_total)}"


def _footer(order: Order, tracking_url: str) -> str:
    lines = [
        "",
        f"Subtotal: {money(order.subtotal)}",
        f"Delivery: {money(order.delivery_charge)}",
        f"Total: {money(order.total)}",
        "",
        f"Deliver to: {order.delivery_address}, {order.delivery_city}",
    ]
    if tracking_url:
        lines += ["", f"Track your order: {tracking_url}"]
    return "\n".join(lines)


def build_order_confirmation_message(order: Order) -> str:
    """The message a *customer* sends to the merchant right after
    checkout — a courtesy notification, not the order channel itself
    (the order already exists in the database by the time this is ever
    called; see ``orders.services.create_order``). Truncates the
    itemised list to fit ``StoreSettings.whatsapp_message_max_chars``,
    per §21: render as many full item lines as fit, then a
    "...and N more items" notice, then the same totals/delivery/tracking
    footer every message gets regardless of truncation.
    """
    max_chars = StoreSettings.load().whatsapp_message_max_chars
    tracking_url = _tracking_url(order)
    header = f"New order {order.order_number}\n\nItems:\n"
    footer = _footer(order, tracking_url)

    items = list(order.items.all())
    item_lines = [_item_line(item, i) for i, item in enumerate(items, start=1)]

    full_message = header + "\n".join(item_lines) + footer
    if len(full_message) <= max_chars:
        return full_message

    included: list[str] = []
    for line in item_lines:
        remaining = len(items) - len(included) - 1
        notice = f"\n…and {remaining} more item{'s' if remaining != 1 else ''}"
        candidate = header + "\n".join([*included, line]) + notice + footer
        if len(candidate) > max_chars:
            break
        included.append(line)

    remaining = len(items) - len(included)
    notice = f"\n…and {remaining} more item{'s' if remaining != 1 else ''}" if remaining else ""
    return header + "\n".join(included) + notice + footer


class _SafeTemplateDict(dict[str, str]):
    """``str.format_map`` support that renders an unrecognised
    ``{placeholder}`` as an empty string instead of raising ``KeyError``
    — a merchant hand-editing a status template in Django admin can typo
    a placeholder name; that should degrade quietly, not 500 the moment
    someone tries to message a customer."""

    def __missing__(self, key: str) -> str:
        return ""


_STATUS_TEMPLATE_FIELDS: dict[str, str] = {
    Order.Status.CONFIRMED: "whatsapp_template_confirmed",
    Order.Status.PROCESSING: "whatsapp_template_processing",
    Order.Status.DISPATCHED: "whatsapp_template_dispatched",
    Order.Status.OUT_FOR_DELIVERY: "whatsapp_template_out_for_delivery",
    Order.Status.DELIVERED: "whatsapp_template_delivered",
    Order.Status.CANCELLED: "whatsapp_template_cancelled",
}


def build_status_update_message(order: Order) -> str:
    """The message a *merchant* sends to a customer for a status change
    (§26) — merchant-initiated (a button click, Stage 10's job to wire
    up), templated per status, editable in store settings. Raises
    ``ValueError`` for a status with no template (§26 only names six of
    the eleven statuses; the others — Pending Confirmation, Ready to
    Dispatch, Failed Delivery, Returned, Expired — have none by design,
    not by omission)."""
    field_name = _STATUS_TEMPLATE_FIELDS.get(order.status)
    if field_name is None:
        raise ValueError(f"No WhatsApp template is defined for status {order.status!r}.")

    template: str = getattr(StoreSettings.load(), field_name)
    context = _SafeTemplateDict(
        customer_name=order.customer_name,
        order_number=order.order_number,
        tracking_number=order.tracking_number,
        courier_name=order.courier_name,
        tracking_url=_tracking_url(order),
    )
    return template.format_map(context)
