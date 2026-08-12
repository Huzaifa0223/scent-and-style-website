"""Service functions — the sanctioned entry points for multi-step catalog
writes that a bare ``Model.objects.create()`` can't safely express alone.

Cross-app communication in this project is by explicit service function
call, not signals (CLAUDE.md) — but that rule is about *cross-app*
coupling. The default-variant invariant here is intra-app (catalog
creating its own ProductVariant), and was previously implemented via
``transaction.on_commit()`` inside ``Product.save()``. That approach was
dropped: ``on_commit`` callbacks never fire inside a test wrapped in a
transaction that's rolled back rather than committed (pytest-django's
default), so the entire safety net was silently inert under the test
suite. This module is the real mechanism; the deferred constraint trigger
in migration 0002 is the backstop for callers that bypass it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from .models import Product, ProductVariant


def _generate_unique_sku(base: str) -> str:
    candidate = base.upper()
    suffix_n = 2
    while ProductVariant.objects.filter(sku=candidate).exists():
        candidate = f"{base.upper()}-{suffix_n}"
        suffix_n += 1
    return candidate


@transaction.atomic
def create_product(
    *,
    default_variant_sku: str | None = None,
    default_variant_price: Decimal = Decimal("0.00"),
    **product_fields: Any,  # noqa: ANN401 — forwarded verbatim to Product(**kwargs)
) -> Product:
    """Create a ``Product`` together with a single auto-generated default
    variant, in one transaction. This is the sanctioned path *only* for
    callers that don't yet know their variants — factories, and any future
    single-variant "quick add" flow.

    It is deliberately **not** used by flows that already have several
    explicit variants in hand — the portal's variant formset (Stage 3) and
    Stage 16's CSV import both create the ``Product`` row and their own
    ``ProductVariant`` rows together in one ``transaction.atomic()`` block
    directly, rather than creating this function's throwaway default variant
    and then editing or deleting it. Those flows still get the "at least one
    variant" guarantee — either from their own pre-save validation (the
    formset's ``clean()`` rejects zero surviving variant forms) or, as a
    backstop for anything that skips validation, from the same deferred
    constraint trigger this function also relies on (catalog/migrations/0002).
    If a caller does end up swapping which variant is default across more
    than one statement, that's safe in any order because
    ``variant_at_most_one_default`` (catalog/migrations/0003) only checks at
    COMMIT, not after each individual UPDATE.
    """
    product = Product(**product_fields)
    product.save()
    sku = default_variant_sku or _generate_unique_sku(f"{product.slug}-default")
    ProductVariant.objects.create(
        product=product,
        sku=sku,
        price=default_variant_price,
        is_default=True,
    )
    return product
