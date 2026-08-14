"""Catalog domain model (requirements §2).

Ordered so every FK points backward, not forward — Brand/Category/Tag have
no catalog dependencies; Product depends on those three; ProductImage
depends on Product; ProductVariant depends on Product and (optionally)
ProductImage; the two attribute-value junction tables come last since they
depend on everything above them.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import (
    BooleanField,
    Case,
    Count,
    F,
    IntegerField,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Now

from core.config import DEFAULT_LOW_STOCK_THRESHOLD
from core.models import TimeStampedModel
from core.slugs import unique_slugify
from core.validators import validate_image_upload_size


class Brand(TimeStampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    logo = models.ImageField(
        upload_to="brands/", blank=True, validators=[validate_image_upload_size]
    )
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Category(TimeStampedModel):
    """Exactly two levels: a top-level category, and its subcategories.

    Enforced in ``clean()`` rather than a CHECK constraint — a self-join
    condition ("my parent's parent must be null") isn't expressible as a
    single-row Postgres CHECK constraint.
    """

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="subcategories"
    )
    description = models.TextField(blank=True, default="")
    image = models.ImageField(
        upload_to="categories/", blank=True, validators=[validate_image_upload_size]
    )
    position = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    meta_title = models.CharField(max_length=70, blank=True, default="")
    meta_description = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["position", "name"]
        indexes = [models.Index(fields=["is_published"])]

    def __str__(self) -> str:
        return self.name

    @property
    def effective_meta_title(self) -> str:
        return self.meta_title or self.name

    @property
    def effective_meta_description(self) -> str:
        return (self.meta_description or self.description)[:160]

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("storefront:category_product_list", kwargs={"category_slug": self.slug})

    def clean(self) -> None:
        super().clean()
        parent = self.parent
        if parent is not None and parent.parent_id is not None:
            raise ValidationError(
                {"parent": "A subcategory cannot itself have a parent — only two levels exist."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        self.clean()
        super().save(*args, **kwargs)


class Tag(TimeStampedModel):
    """Free-form product labels — searchable (§15) and used for facets."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class AttributeDefinition(TimeStampedModel):
    """One vocabulary serves both faceted filtering and variant definition
    (§2.2) — ``is_filterable`` and ``is_variant_option`` are independent
    flags, not a single "type" choice, because an attribute can be both."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110, unique=True)
    is_filterable = models.BooleanField(default=False)
    is_variant_option = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class AttributeValue(TimeStampedModel):
    definition = models.ForeignKey(
        AttributeDefinition, on_delete=models.CASCADE, related_name="values"
    )
    value = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "slug"], name="attributevalue_unique_definition_slug"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.definition.name}: {self.value}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(
                self, self.value, extra_filters={"definition_id": self.definition_id}
            )
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet["Product"]):
    def with_pricing(self) -> ProductQuerySet:
        """Annotate ``display_price`` (min price across active variants) and
        ``has_price_range`` in one query — a Python ``@property`` computing
        either would re-query per instance, failing Stage 6's
        ``assertNumQueries`` gate on any list view. Products with zero
        active variants get ``display_price=None``.
        """
        return self.annotate(
            display_price=Min("variants__price", filter=Q(variants__is_active=True)),
            _active_price_count=Count(
                "variants__price", filter=Q(variants__is_active=True), distinct=True
            ),
        ).annotate(
            has_price_range=Case(
                When(_active_price_count__gt=1, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )


class Product(TimeStampedModel):
    """The marketing unit — one PDP, one URL, one gallery. Carries no price
    and no stock; both live on ProductVariant (C1 in requirements §0)."""

    objects = ProductQuerySet.as_manager()

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    subcategory = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products_as_subcategory",
    )
    short_description = models.CharField(max_length=300, blank=True, default="")
    description = models.TextField(blank=True, default="")
    tags = models.ManyToManyField(Tag, blank=True, related_name="products")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField(default=False)
    meta_title = models.CharField(max_length=70, blank=True, default="")
    meta_description = models.CharField(max_length=160, blank=True, default="")
    # Denormalised search column (§15) — populated by Stage 5's rebuild
    # signal/management command. Deliberately empty until then.
    search_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            # fastupdate=False: GIN's default defers new entries to an
            # unordered "pending list", flushed only by VACUUM — until
            # that runs, the planner's cost estimate for this index is
            # wrong (it prices in scanning the whole pending list) and it
            # silently falls back to a sequential scan, with no error.
            # For a single merchant whose catalog edits are infrequent and
            # manual but whose search reads are constant, that's a real
            # production risk, not just a test-authoring inconvenience —
            # see specs/state.md's Stage 5 notes.
            GinIndex(
                SearchVector("search_text", config="simple"),
                name="product_search_tsv_gin",
                fastupdate=False,
            ),
            GinIndex(
                fields=["search_text"],
                name="product_search_trgm_gin",
                opclasses=["gin_trgm_ops"],
                fastupdate=False,
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def effective_meta_title(self) -> str:
        """§34's "sensible generated default" — the merchant-set
        ``meta_title`` if there is one, else the product name. Never
        blank, so every PDP has a real ``<title>``/``og:title`` without
        every product needing its SEO fields hand-filled first."""
        return self.meta_title or self.name

    @property
    def effective_meta_description(self) -> str:
        return (self.meta_description or self.short_description or self.description)[:160]

    def clean(self) -> None:
        super().clean()
        subcategory = self.subcategory
        if subcategory is not None and self.category_id is not None:
            if subcategory.parent_id != self.category_id:
                raise ValidationError(
                    {"subcategory": "Subcategory must be a child of the selected category."}
                )

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("storefront:product_detail", kwargs={"slug": self.slug})

    @property
    def default_variant(self) -> ProductVariant | None:
        """The variant §34's Product JSON-LD prices its ``offers`` off —
        ``is_default`` if one exists, else the first by position. Reads
        ``self.variants.all()``, which returns the ``prefetch_related()``
        cache when the caller prefetched ``"variants"`` first (every
        current caller does — the PDP and the product-listing cards, both
        proven flat by ``assertNumQueries``) and issues a fresh query
        otherwise, the same N+1 contract every "one related object per
        parent" property in this codebase relies on prefetching for.
        """
        variants = list(self.variants.all())
        return next((v for v in variants if v.is_default), variants[0] if variants else None)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Read before either branch below decides the new slug value, so
        # both "merchant typed a new slug" and "merchant cleared it to
        # force regeneration" are captured uniformly — see the class-level
        # ProductSlugRedirect docstring for why this lives here rather
        # than in the portal view: save() is the one path every caller
        # (portal, Django admin, a future bulk script) already goes
        # through, the same reasoning slug auto-generation itself uses.
        previous_slug: str | None = None
        if self.pk is not None:
            previous_slug = (
                type(self)
                ._default_manager.filter(pk=self.pk)
                .values_list("slug", flat=True)
                .first()
            )

        if not self.slug:
            self.slug = unique_slugify(
                self,
                self.name,
                extra_taken_slugs=lambda: set(
                    ProductSlugRedirect.objects.values_list("old_slug", flat=True)
                ),
            )

        if previous_slug and previous_slug != self.slug:
            ProductSlugRedirect.objects.get_or_create(
                old_slug=previous_slug, defaults={"product": self}
            )

        self.clean()
        super().save(*args, **kwargs)


class ProductSlugRedirect(TimeStampedModel):
    """Old slug -> current product (§34, roadmap Stage 12): a merchant-
    initiated slug change must not break a link someone already has.
    Written automatically by ``Product.save()`` whenever an existing
    product's slug actually changes — never by a portal view directly,
    so a slug change made through the sanctioned edit path can't happen
    without a matching redirect also being created.

    ``product`` is an FK, not a snapshotted "current slug" string — so a
    product renamed twice needs no bookkeeping to keep older redirect
    rows pointing at the *latest* slug: ``storefront.views.
    ProductDetailView`` resolves ``old_slug`` to ``product.slug`` at
    lookup time, which is always wherever the product's slug is *now*,
    not whatever it was at the moment this row was written. ``old_slug``
    is unique — one historical slug can only ever mean one product, or a
    redirect would be ambiguous about which product to send a visitor to.
    ``on_delete=CASCADE``: a redirect to a product that no longer exists
    at all has nothing left to redirect to.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="slug_redirects")
    # max_length matches Product.slug exactly (220) — a mismatch here
    # would silently truncate or reject a capture for a product whose
    # slug is long enough to hit the difference; a dedicated test proves
    # a max-length slug round-trips, not just that the numbers match on
    # paper. unique=True alone already creates the index Postgres needs
    # for the redirect lookup — no separate db_index=True, the same
    # choice Product.slug itself makes.
    old_slug = models.SlugField(max_length=220, unique=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.old_slug} -> {self.product.slug}"


class ProductImage(TimeStampedModel):
    """On save, generates three WebP+JPEG derivative pairs synchronously
    (§2.5) — see core/images.py for why synchronous is deliberate, not
    an oversight.

    ``is_primary`` allows at most one ``True`` row per product, via a
    deferred constraint trigger (catalog/migrations/0005) rather than a
    partial unique index — the fourth invariant on this project to hit the
    same wall (Postgres/Django forbid combining a unique constraint's
    ``condition`` with ``deferrable``): an immediate partial index would
    force every primary-image swap into a specific unset-then-set statement
    order, which the portal's image-management form (reorder + re-primary +
    delete, all in one submit — Stage 3) can't guarantee any more than the
    variant formset could guarantee it for the default variant.

    ``delete()`` below promotes the next image by position when the deleted
    row was primary, mirroring ``ProductVariant.delete()`` — including the
    same guard (only promote if no *other* image already holds
    ``is_primary=True``), for the same reason: saving an explicit
    reassignment before deleting the old primary must not race a second,
    unwanted promotion onto a third, unrelated image.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to="products/originals/", validators=[validate_image_upload_size]
    )
    alt_text = models.CharField(max_length=255, blank=True, default="")
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    thumb_webp = models.ImageField(upload_to="products/thumb/", blank=True)
    thumb_jpeg = models.ImageField(upload_to="products/thumb/", blank=True)
    card_webp = models.ImageField(upload_to="products/card/", blank=True)
    card_jpeg = models.ImageField(upload_to="products/card/", blank=True)
    full_webp = models.ImageField(upload_to="products/full/", blank=True)
    full_jpeg = models.ImageField(upload_to="products/full/", blank=True)

    class Meta:
        ordering = ["position", "id"]
        # No Django-level uniqueness constraint on is_primary: see the
        # class docstring above. Enforced by a deferred constraint trigger
        # instead (catalog/migrations/0005).

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # A brand-new instance's "original" image is None regardless of what
        # was just passed via kwargs — self.pk is only set for a row that
        # actually came from the database (via from_db, not __init__(**kw)),
        # so checking it here is what distinguishes "loaded" from "new".
        self._original_image_name: str | None = (
            self.image.name if (self.pk and self.image) else None
        )

    def __str__(self) -> str:
        return f"{self.product.name} image {self.position}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        from core.images import DERIVATIVE_SPECS, resize_and_encode

        if not self.alt_text and self.product_id:
            self.alt_text = self.product.name
        if self.is_primary is False and not self.pk and not self.product.images.exists():
            self.is_primary = True

        image_changed = bool(self.image) and self.image.name != self._original_image_name
        super().save(*args, **kwargs)

        if image_changed:
            source = self.image.file
            for spec in DERIVATIVE_SPECS:
                webp_file = resize_and_encode(source, spec.max_dimension, "WEBP")
                getattr(self, f"{spec.name}_webp").save(webp_file.name, webp_file, save=False)
                jpeg_file = resize_and_encode(source, spec.max_dimension, "JPEG")
                getattr(self, f"{spec.name}_jpeg").save(jpeg_file.name, jpeg_file, save=False)
            update_fields = [
                f"{spec.name}_{fmt}" for spec in DERIVATIVE_SPECS for fmt in ("webp", "jpeg")
            ]
            super().save(update_fields=update_fields)
            self._original_image_name = self.image.name

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        product = self.product
        was_primary = self.is_primary
        result = super().delete(*args, **kwargs)
        if was_primary and not product.images.filter(is_primary=True).exists():
            next_image = product.images.order_by("position", "id").first()
            if next_image is not None:
                next_image.is_primary = True
                next_image.save(update_fields=["is_primary", "updated_at"])
        return result


class ProductVariantQuerySet(models.QuerySet["ProductVariant"]):
    def with_available_quantity(self) -> ProductVariantQuerySet:
        """Annotate ``reserved_quantity``, ``available_quantity``,
        ``is_in_stock``, and ``is_low_stock`` in one query — the same
        bundling ``ProductQuerySet.with_pricing()`` uses for
        ``has_price_range``, deliberately not a Python ``@property``: a
        property here would be the exact N+1 CLAUDE.md's Traps section
        warns against the moment anything iterates a queryset of variants
        without this method.

        ``available_quantity`` = ``stock_quantity`` minus
        ``reserved_quantity`` (active, unexpired reservations — §10.1) —
        the customer-facing "can this be bought right now" number, and
        what ``is_in_stock`` derives from. ``is_low_stock`` derives from
        ``stock_quantity`` instead, deliberately *not*
        ``available_quantity`` — it's a merchant-facing reorder signal
        ("I have 3 left on the shelf"), and §10.5 lists on-hand, reserved,
        available, low-stock, and out-of-stock as five separate columns,
        not four derived from one number. Basing it on availability would
        make it flicker on and off as unrelated reservations are created
        and expire against the same physical stock, telling a merchant to
        reorder when they have plenty on the shelf and simply a lot of
        pending WhatsApp orders.

        ``reserved_quantity`` is a correlated ``Subquery``, not a
        ``Sum(..., filter=)`` join-based aggregate. ``with_pricing()``
        isn't precedent for the join form here: that method is on
        ``Product`` with no second to-many relation routinely joined
        alongside it, but this one is on ``ProductVariant``, which already
        has another to-many reverse relation (``variant_attribute_values``)
        that attribute filtering joins routinely, and Stage 6's listing
        page is expected to combine variant availability with other
        per-variant joins too. A join-based ``Sum`` here would silently
        multiply the moment a caller's queryset joins that second
        relation — two to-many tables joined into one query multiply rows
        before ``GROUP BY`` collapses them back down, so the sum overcounts
        by a factor of however many rows the other join matched. A
        ``Subquery`` is evaluated independently per outer row and cannot
        be affected by whatever else the caller's queryset joins.
        Verified empirically:
        ``test_with_available_quantity_does_not_fan_out_with_a_variant_attribute_join``
        fails under the join-based form and passes under this one.

        Resolves ``StockReservation`` via ``django.apps.apps.get_model()``
        rather than a top-level ``from inventory.models import
        StockReservation`` — catalog must not import from an app that
        depends on it (the same direction CLAUDE.md states for
        catalog/orders), and this keeps that true at the Python import
        graph level while still building a real queryset for the
        ``Subquery``.

        Compares against the database's clock (``Now()``), not Python's
        ``timezone.now()`` — the same predicate this annotation uses to
        decide "active" is what ``inventory.services.reserve()`` uses
        under its row lock and what the sweeper's bulk delete uses; three
        call sites deciding the same question from two different clocks
        is a real inconsistency, not a theoretical one.
        """
        stock_reservation = apps.get_model("inventory", "StockReservation")
        reserved_subquery = (
            stock_reservation.objects.filter(variant=OuterRef("pk"), expires_at__gt=Now())
            .order_by()
            .values("variant")
            .annotate(total=Sum("quantity"))
            .values("total")
        )
        reserved_quantity = Coalesce(
            Subquery(reserved_subquery, output_field=IntegerField()), Value(0)
        )
        return (
            self.annotate(reserved_quantity=reserved_quantity)
            .annotate(
                available_quantity=F("stock_quantity") - F("reserved_quantity"),
            )
            .annotate(
                is_in_stock=Case(
                    When(available_quantity__gt=0, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
                is_low_stock=Case(
                    When(
                        Q(stock_quantity__gt=0) & Q(stock_quantity__lte=F("low_stock_threshold")),
                        then=Value(True),
                    ),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
            )
        )


class ProductVariant(TimeStampedModel):
    """The purchasable unit — what goes in a cart, what has stock. Every
    product has at least one — enforced by ``catalog.services.create_product``
    plus a deferred database constraint trigger as the backstop for any path
    that doesn't go through it (see catalog/migrations/0002).

    ``is_default`` allows at most one ``True`` row per product, also via a
    deferred constraint trigger (catalog/migrations/0003) rather than a
    partial unique index — Postgres/Django forbid combining a unique
    constraint's ``condition`` with ``deferrable``, and a plain immediate
    partial index would force every default-variant swap (Stage 3's formset:
    unset the old default, set a new one) to happen in a specific
    unset-then-set statement order to avoid a transient two-defaults state.
    Deferring the check to COMMIT makes the invariant order-independent,
    same reasoning as the "at least one variant" trigger above.

    The trigger only covers INSERT/UPDATE, not DELETE — deleting the row
    that happens to be the default doesn't fire it, and would silently
    leave the product with zero defaults. ``delete()`` below promotes the
    next variant by position, mirroring ``ProductImage.delete()``'s
    primary-image promotion, so "every product has a default variant" holds
    for as long as it has any variant at all, not just at creation time.

    That promotion only fires if no *other* variant already holds
    ``is_default=True``. Without that guard, a caller that explicitly
    assigns a new default before deleting the old one (Stage 3's portal
    formset: save survivors first, delete removed variants second, so the
    deferred trigger's transient-multi-default tolerance during the request
    doesn't matter) would race against the auto-promotion picking a third,
    unrelated variant by position — briefly leaving two rows with
    ``is_default=True`` and failing the deferred trigger at commit for a
    reason that has nothing to do with the actual edit. The guard assumes
    "at most one default" already held before the delete — that's the
    deferred trigger's job, not this method's; if it didn't hold, this
    method now leaves the pre-existing extra default in place rather than
    also promoting a second one, which is the safer of two wrong outcomes,
    not a fix for the underlying corruption.

    ``attribute_signature`` uniqueness per product is the same story a third
    time (catalog/migrations/0004): a plain partial unique index forces
    every request that changes two variants' attribute sets in one
    transaction — swapping 50ml/100ml between two variants, or deleting one
    variant and reassigning its attributes to a survivor — into a specific
    statement order that avoids ever holding a transient duplicate, which
    Stage 3's formset (saves survivors in form order, not attribute-aware
    order) can't guarantee. Deferred to COMMIT for the same reason as the
    other two.
    """

    objects = ProductVariantQuerySet.as_manager()

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=DEFAULT_LOW_STOCK_THRESHOLD)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    length_mm = models.PositiveIntegerField(null=True, blank=True)
    width_mm = models.PositiveIntegerField(null=True, blank=True)
    height_mm = models.PositiveIntegerField(null=True, blank=True)
    image = models.ForeignKey(
        ProductImage, null=True, blank=True, on_delete=models.SET_NULL, related_name="variants"
    )
    is_default = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Sorted, comma-joined AttributeValue ids for this variant — the only
    # way to turn "two variants with an identical attribute set" into a real
    # database IntegrityError rather than an application-level check, since
    # set-equality across rows isn't expressible as a column-level UNIQUE.
    attribute_signature = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["position", "id"]
        # No Django-level uniqueness constraint on attribute_signature: see
        # the class docstring above. Enforced by a deferred constraint
        # trigger instead (catalog/migrations/0004).

    def __str__(self) -> str:
        return self.sku

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        product = self.product
        was_default = self.is_default
        result = super().delete(*args, **kwargs)
        if was_default and not product.variants.filter(is_default=True).exists():
            next_variant = product.variants.order_by("position", "id").first()
            if next_variant is not None:
                next_variant.is_default = True
                next_variant.save(update_fields=["is_default", "updated_at"])
        return result

    @property
    def discount_percent(self) -> int | None:
        if self.compare_at_price is None or self.compare_at_price <= self.price:
            return None
        return round((self.compare_at_price - self.price) / self.compare_at_price * 100)

    @property
    def display_label(self) -> str:
        """Human-readable variant identity — "Red / 50ml", or the SKU for
        a variant with no attribute values. Shared by the PDP's variant
        `<select>` (storefront) and `OrderItem.variant_label`'s snapshot
        (orders), rather than two copies that can drift. Reads
        ``variant_attribute_values.all()`` — N+1-safe only when the caller
        has prefetched ``variant_attribute_values__value``; it does not
        prefetch for itself, same as every other relation-reading property
        on this model."""
        values = [vav.value.value for vav in self.variant_attribute_values.all()]
        return " / ".join(values) if values else self.sku

    def compute_attribute_signature(self) -> str:
        # sorted() on a list of int value_ids is a numeric sort — sorting
        # the stringified/joined form instead would put id 10 before id 2.
        value_ids = sorted(self.variant_attribute_values.values_list("value_id", flat=True))
        return ",".join(str(v) for v in value_ids)

    def sync_attribute_signature(self) -> None:
        new_signature = self.compute_attribute_signature()
        if new_signature != self.attribute_signature:
            self.attribute_signature = new_signature
            self.save(update_fields=["attribute_signature", "updated_at"])


class ProductAttributeValue(TimeStampedModel):
    """Non-variant facets — e.g. a product is Unisex; that doesn't create a
    variant (§2.2)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    value = models.ForeignKey(
        AttributeValue, on_delete=models.CASCADE, related_name="product_attribute_values"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "value"], name="productattributevalue_unique_product_value"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name}: {self.value}"


class VariantAttributeValue(TimeStampedModel):
    """The combination that defines a variant — a 50ml Red variant has two
    of these rows. save()/delete() keep the owning variant's
    ``attribute_signature`` in sync, which is what makes the uniqueness
    constraint on ProductVariant actually mean something."""

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="variant_attribute_values"
    )
    value = models.ForeignKey(
        AttributeValue, on_delete=models.CASCADE, related_name="variant_attribute_values"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "value"], name="variantattributevalue_unique_variant_value"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant.sku}: {self.value}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        self.variant.sync_attribute_signature()

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        variant = self.variant
        result = super().delete(*args, **kwargs)
        variant.sync_attribute_signature()
        return result
