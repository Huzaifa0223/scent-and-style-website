"""Catalog domain model (requirements §2).

Ordered so every FK points backward, not forward — Brand/Category/Tag have
no catalog dependencies; Product depends on those three; ProductImage
depends on Product; ProductVariant depends on Product and (optionally)
ProductImage; the two attribute-value junction tables come last since they
depend on everything above them.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import BooleanField, Case, Count, F, Min, Q, Value, When

from core.config import DEFAULT_LOW_STOCK_THRESHOLD
from core.models import TimeStampedModel
from core.slugs import unique_slugify


class Brand(TimeStampedModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    logo = models.ImageField(upload_to="brands/", blank=True)
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
    image = models.ImageField(upload_to="categories/", blank=True)
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
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        subcategory = self.subcategory
        if subcategory is not None and self.category_id is not None:
            if subcategory.parent_id != self.category_id:
                raise ValidationError(
                    {"subcategory": "Subcategory must be a child of the selected category."}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        self.clean()
        super().save(*args, **kwargs)


class ProductImage(TimeStampedModel):
    """On save, generates three WebP+JPEG derivative pairs synchronously
    (§2.5) — see core/images.py for why synchronous is deliberate, not
    an oversight."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/originals/")
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
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="productimage_one_primary_per_product",
            ),
        ]

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
        if was_primary:
            next_image = product.images.order_by("position", "id").first()
            if next_image is not None:
                next_image.is_primary = True
                next_image.save(update_fields=["is_primary", "updated_at"])
        return result


class ProductVariantQuerySet(models.QuerySet["ProductVariant"]):
    def with_available_quantity(self) -> ProductVariantQuerySet:
        """Annotate ``available_quantity``. Stage 4 changes the expression
        here (subtracting active reservations) — call sites don't change,
        which is the point: nothing downstream ever branches on how
        availability is computed, only on the annotated value.
        """
        return self.annotate(available_quantity=F("stock_quantity"))


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
        constraints = [
            # Blank signatures are excluded: a variant is created before its
            # VariantAttributeValue rows can point at it (they need its pk),
            # so it necessarily sits at "" for a moment — and the
            # auto-created default variant may legitimately stay at "" for
            # its whole life on a single-variant product. Only non-blank
            # (real) attribute sets need to be unique per product.
            models.UniqueConstraint(
                fields=["product", "attribute_signature"],
                condition=~Q(attribute_signature=""),
                name="variant_unique_attribute_set_per_product",
            ),
        ]

    def __str__(self) -> str:
        return self.sku

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        product = self.product
        was_default = self.is_default
        result = super().delete(*args, **kwargs)
        if was_default:
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
    def is_in_stock(self) -> bool:
        """Reads ``stock_quantity`` directly, not the annotated
        ``available_quantity`` — Stage 4 revisits this once reservations
        exist and availability can differ from on-hand stock."""
        return self.stock_quantity > 0

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.stock_quantity <= self.low_stock_threshold

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
