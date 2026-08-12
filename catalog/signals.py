"""Wires ``search_indexing.rebuild_search_text`` to every save/delete that
can change what it computes (§15) — the one signal-based mechanism in this
project (see ``search_indexing``'s module docstring for why).

Not wired here: ``Brand``/``Category`` rename cascading to every product in
that brand/category. That would be an unbounded fan-out write per rename,
so it's the ``rebuild_search_index`` management command's job (a deliberate
resync), not a live signal. Stage 5's gate 2 only requires a *product*
rename to self-update, which this module covers.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from catalog.models import (
    Product,
    ProductAttributeValue,
    ProductVariant,
    VariantAttributeValue,
)
from catalog.search_indexing import rebuild_search_text


@receiver(post_save, sender=Product)
def _on_product_saved(instance: Product, **kwargs: Any) -> None:
    rebuild_search_text(instance)


@receiver(post_save, sender=ProductVariant)
@receiver(post_delete, sender=ProductVariant)
def _on_variant_changed(instance: ProductVariant, **kwargs: Any) -> None:
    rebuild_search_text(instance.product)


@receiver(post_save, sender=ProductAttributeValue)
@receiver(post_delete, sender=ProductAttributeValue)
def _on_product_attribute_value_changed(instance: ProductAttributeValue, **kwargs: Any) -> None:
    rebuild_search_text(instance.product)


@receiver(post_save, sender=VariantAttributeValue)
@receiver(post_delete, sender=VariantAttributeValue)
def _on_variant_attribute_value_changed(instance: VariantAttributeValue, **kwargs: Any) -> None:
    rebuild_search_text(instance.variant.product)


@receiver(m2m_changed, sender=Product.tags.through)
def _on_product_tags_changed(
    instance: Any, action: str, reverse: bool, pk_set: set[int] | None, **kwargs: Any
) -> None:
    if action not in {"post_add", "post_remove", "post_clear"}:
        return
    products: list[Product]
    if reverse:
        products = list(Product.objects.filter(pk__in=pk_set or []))
    elif isinstance(instance, Product):
        products = [instance]
    else:
        products = []
    for product in products:
        rebuild_search_text(product)
