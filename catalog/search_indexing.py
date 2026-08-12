"""Computes ``Product.search_text`` (§15) — the denormalised column
``search.backends.PostgresSearchBackend`` matches and ranks against.

Lives in ``catalog``, not ``search``, because every source field it reads
(name, brand, variant SKUs, category, tags, filterable attribute values) is
catalog's own data. ``search`` only ever reads the finished column; it never
recomputes it — that keeps the "catalog must not import from orders" style
app-boundary rule intact in the other direction (search depends on catalog,
never the reverse).

This is the one signal-based cross-app mechanism in the project (see
CLAUDE.md's "Cross-app communication is by explicit service function call,
not signals — except the search-index rebuild"). ``catalog/signals.py``
wires ``rebuild_search_text`` to the saves/deletes that can change its
inputs; ``search``'s ``rebuild_search_index`` management command calls
``compute_search_text`` directly for a full-catalog resync.
"""

from __future__ import annotations

from catalog.models import Product, VariantAttributeValue


def _filterable_variant_attribute_values(product: Product) -> set[str]:
    """Filterable attribute values attached through any of this product's
    variants (Red, 50ml, ...) — a separate junction table from
    ``ProductAttributeValue``, so it needs its own query."""
    return set(
        VariantAttributeValue.objects.filter(
            variant__product=product, value__definition__is_filterable=True
        ).values_list("value__value", flat=True)
    )


def compute_search_text(product: Product) -> str:
    """Builds the denormalised, pre-lowercased search blob.

    Pre-lowering here — once, at write time — is what lets both GIN index
    expressions and every query stay free of their own ``lower()``
    wrapping, which would otherwise have to be duplicated in the index
    definition, the tsvector match, and the trigram match to stay
    index-compatible.

    Filterable attribute values are pulled from both ``ProductAttributeValue``
    (product-level facets, e.g. Unisex) and ``VariantAttributeValue`` (the
    values that define this product's own variants, e.g. Red, 50ml) —
    non-filterable attributes (internal-only vocabulary) are deliberately
    excluded, matching what a customer would actually search for rather
    than the full internal attribute set.
    """
    parts: list[str] = [product.name, product.category.name]
    if product.brand_id is not None:
        parts.append(product.brand.name)
    if product.subcategory_id is not None:
        parts.append(product.subcategory.name)
    parts.extend(product.variants.values_list("sku", flat=True))
    parts.extend(product.tags.values_list("name", flat=True))

    filterable_values: set[str] = set()
    filterable_values.update(
        product.attribute_values.filter(value__definition__is_filterable=True).values_list(
            "value__value", flat=True
        )
    )
    filterable_values.update(_filterable_variant_attribute_values(product))
    parts.extend(sorted(filterable_values))

    return " ".join(part for part in parts if part).lower()


def rebuild_search_text(product: Product) -> bool:
    """Recomputes and writes ``search_text`` for one product, if it changed.

    Uses ``QuerySet.update()`` rather than ``product.save()`` deliberately:
    ``update()`` never emits ``post_save``, so this can be called from
    inside a ``post_save``/``post_delete`` receiver (see
    ``catalog/signals.py``) without any risk of recursing back into itself
    — no ``update_fields`` guard needed, the write path structurally can't
    re-trigger the signal that called it.
    """
    new_text = compute_search_text(product)
    if new_text == product.search_text:
        return False
    Product.objects.filter(pk=product.pk).update(search_text=new_text)
    product.search_text = new_text
    return True
