"""Customer service functions — the only sanctioned way to resolve a
checkout submission to a ``Customer`` row.
"""

from __future__ import annotations

from .models import Customer


def get_or_create_customer(*, name: str, phone: str, whatsapp_number: str, email: str) -> Customer:
    """``phone`` must already be E.164-normalised by the caller (checkout's
    form does this before calling in). Matches on ``phone`` (§29); on a
    repeat customer, updates ``name``/``whatsapp_number``/``email`` from
    this order's submission, but only for fields that were actually
    submitted non-empty — a blank email on this order must not overwrite
    a known one from a previous order.

    ``Customer.phone`` is ``unique=True``, so two checkouts for a brand
    new phone number at the same instant are a real race.
    ``update_or_create()`` handles it without any extra code here: Django
    5.2's implementation takes ``select_for_update()`` on both its initial
    lookup *and* its post-``IntegrityError`` retry (verified directly
    against the installed ``django.db.models.query`` source, not assumed
    from the docs), so the loser blocks on the winner's lock and returns
    the winner's row — it does not re-raise past this function. An earlier
    draft of this function caught that ``IntegrityError`` explicitly and
    re-fetched; removed, since that branch is unreachable under any
    scenario this codebase can actually produce (nothing ever deletes a
    ``Customer`` mid-race) and unreachable code is a real coverage-floor
    problem, not just clutter, at this project's 90% floor on ``orders``.
    """
    defaults: dict[str, str] = {"name": name}
    if whatsapp_number:
        defaults["whatsapp_number"] = whatsapp_number
    if email:
        defaults["email"] = email
    customer, _ = Customer.objects.update_or_create(phone=phone, defaults=defaults)
    return customer
