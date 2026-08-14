"""Generic slug generation with collision handling.

Shared by every catalog model that has a stable slug (Product, Category,
Brand, Tag, AttributeDefinition, AttributeValue): generate from a source
string only when the slug is blank, so a later name change never silently
rewrites an existing, possibly-linked-to slug (roadmap Stage 2 — stability
is deliberate; see Stage 12 for the redirect mechanism that handles the
opt-in case).
"""

from __future__ import annotations

from collections.abc import Callable

from django.db.models import Model
from django.utils.text import slugify


def unique_slugify(
    instance: Model,
    source: str,
    *,
    slug_field: str = "slug",
    max_length: int = 255,
    extra_filters: dict[str, object] | None = None,
    extra_taken_slugs: Callable[[], set[str]] | None = None,
) -> str:
    """Return a slug derived from ``source``, unique within ``instance``'s model.

    Appends ``-2``, ``-3``, ... on collision. ``extra_filters`` narrows the
    uniqueness scope (e.g. ``{"definition_id": ...}`` for ``AttributeValue``,
    which is unique per-definition rather than project-wide).

    ``extra_taken_slugs`` — a callable returning a set of additional
    forbidden values — lets a caller avoid colliding with slugs this
    generic helper has no business knowing about (roadmap Stage 12:
    ``Product`` avoids generating a fresh slug that matches an existing
    ``catalog.ProductSlugRedirect.old_slug``, so a brand-new product
    never silently steals another product's historical link). A callable
    rather than a plain set/queryset so the caller only pays for building
    it when a collision loop actually needs to check it.
    """
    base = slugify(source)[:max_length] or "item"
    candidate = base
    model_cls = instance.__class__
    queryset = model_cls._default_manager.all()
    if extra_filters:
        queryset = queryset.filter(**extra_filters)
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    taken_extra = extra_taken_slugs() if extra_taken_slugs is not None else set()

    suffix_n = 2
    while queryset.filter(**{slug_field: candidate}).exists() or candidate in taken_extra:
        suffix = f"-{suffix_n}"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        suffix_n += 1
    return candidate
