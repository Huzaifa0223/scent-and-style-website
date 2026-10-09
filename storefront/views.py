"""Storefront views (roadmap Stage 6, §16-17). Public — no permission
mixin, unlike everything in ``portal``.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import (
    Avg,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
)
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import DetailView, FormView, ListView

from catalog.models import (
    AttributeDefinition,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductQuerySet,
    ProductSlugRedirect,
    ProductVariant,
)
from core.config import HOME_BRANDS_LIMIT, RELATED_PRODUCTS_LIMIT, TRENDING_WINDOW_DAYS
from core.models import RateLimitScope
from core.ratelimit import (
    RateLimitedError,
    RateLimitPolicy,
    check_rate_limit,
    client_ip,
    record_attempt,
)
from core.templatetags.money import money
from orders.forms import ProductReviewForm
from orders.models import Order, OrderItem, ProductReview
from orders.reviews import submit_product_review
from store.models import StoreSettings
from storefront import seo
from storefront.filtering import (
    apply_filters,
    attribute_facet_counts,
    brand_facet_counts,
    filters_from_query_params,
)

STOREFRONT_PAGE_SIZE = 24
"""A 4- or 6-column desktop grid divides evenly into 24 with no partial
final row for either layout — not chosen to satisfy a test."""

_SORT_OPTIONS = {
    "newest": ("-created_at",),
    "price_asc": ("display_price",),
    "price_desc": ("-display_price",),
    "featured": ("-is_featured", "-created_at"),
}

_FRAGRANCE_NOTE_LINE = re.compile(
    r"^\s*(top|head|heart|middle|base)\s+notes?\s*:\s*(.*?)\s*$", re.IGNORECASE
)


def _split_legacy_fragrance_notes(description: str) -> tuple[dict[str, str], str]:
    """Promote explicitly labeled legacy fragrance-note lines for the PDP.

    Catalog descriptions predate the structured note fields, so only lines
    with a recognized label are moved; all other description text is kept.
    """
    notes: dict[str, str] = {}
    remaining_lines: list[str] = []
    labels = {"top": "top", "head": "top", "heart": "heart", "middle": "heart", "base": "base"}
    for line in description.splitlines():
        match = _FRAGRANCE_NOTE_LINE.match(line)
        if match is None or not match.group(2):
            remaining_lines.append(line)
            continue
        notes[labels[match.group(1).casefold()]] = match.group(2)
    return notes, "\n".join(remaining_lines).strip()


DEFAULT_SORT = "newest"
PRODUCT_REVIEW_RATE_LIMIT = RateLimitPolicy(max_attempts=5, window_seconds=3600)


def _attach_json_ld(products: list[Product], *, request: HttpRequest) -> None:
    """Sets a plain, non-model ``.json_ld`` attribute on each product for
    ``_product_card.html`` to render — the same idiom Django's own
    ``Prefetch(to_attr=...)`` already uses on these exact querysets
    (``primary_image_list``). Must run *after* the queryset is fully
    evaluated (a paginated list, not a lazy queryset) so this is one pass
    over already-fetched Python objects, not a trigger for N+1: each
    product's ``.default_variant`` and ``.primary_image_list`` both read
    prefetch caches the caller's own queryset already populated, per
    ``storefront.seo``'s own module docstring.

    ``StoreSettings.load()`` is called exactly once here, outside the
    loop, for the same reason — this project's cache is the database
    cache backend, so calling it per card would be a real query per
    card, not a free hit. Caught by re-running the Stage 6 listing/home
    ``assertNumQueries`` guards right after this function was first
    wired in, not discovered later.
    """
    currency = StoreSettings.load().currency
    for product in products:
        # primary_image_list is Prefetch(to_attr=...)'s runtime-only
        # attribute — django-stubs can't see it statically, same as every
        # other to_attr access in this codebase.
        image_list: list[ProductImage] = product.primary_image_list  # type: ignore[attr-defined]
        primary_image = image_list[0] if image_list else None
        product.json_ld = seo.product_json_ld(  # type: ignore[attr-defined]
            product, request=request, primary_image=primary_image, currency=currency
        )


class ProductListView(ListView[Product]):
    """Serves both ``/products/`` (no category constraint) and
    ``/category/<slug>/`` (the category comes from the URL, not the query
    string) — one view, since every other facet behaves identically on
    both pages. See ``storefront/filtering.py`` for why every
    variant-touching filter is an ``Exists()`` subquery, never a join.
    """

    model = Product
    template_name = "storefront/product_list.html"
    context_object_name = "products"
    paginate_by = STOREFRONT_PAGE_SIZE

    def get_queryset(self) -> QuerySet[Product]:
        base: ProductQuerySet = Product.objects.filter(
            status=Product.Status.PUBLISHED
        ).select_related("brand", "category", "subcategory")
        self.filters = filters_from_query_params(
            self.request.GET, category_slug=self.kwargs.get("category_slug", "")
        )
        filtered = apply_filters(base, self.filters)

        sort_key = self.request.GET.get("sort", DEFAULT_SORT)
        order_fields = _SORT_OPTIONS.get(sort_key, _SORT_OPTIONS[DEFAULT_SORT])

        return (
            filtered.with_pricing()
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.filter(is_primary=True),
                    to_attr="primary_image_list",
                ),
                Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
            )
            .order_by(*order_fields, "-created_at")
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        base: ProductQuerySet = Product.objects.filter(status=Product.Status.PUBLISHED)
        context["category"] = (
            get_object_or_404(Category, slug=self.kwargs["category_slug"])
            if "category_slug" in self.kwargs
            else None
        )
        context["brand_facets"] = brand_facet_counts(base, self.filters)
        context["attribute_facets"] = [
            {
                "definition": definition,
                "values": [
                    {
                        "value": entry["value"],
                        "count": entry["count"],
                        "is_active": entry["value"].slug
                        in self.filters.attribute_groups.get(definition.slug, []),
                    }
                    for entry in attribute_facet_counts(base, self.filters, definition)
                ],
            }
            for definition in AttributeDefinition.objects.filter(is_filterable=True)
        ]
        context["current_sort"] = self.request.GET.get("sort", DEFAULT_SORT)
        context["current_brand"] = self.filters.brand_slug
        context["current_price_min"] = self.request.GET.get("price_min", "")
        context["current_price_max"] = self.request.GET.get("price_max", "")
        context["active_filter_count"] = (
            int(bool(self.filters.brand_slug))
            + int(self.filters.price_min is not None)
            + int(self.filters.price_max is not None)
            + sum(len(values) for values in self.filters.attribute_groups.values())
        )

        _attach_json_ld(context["products"], request=self.request)
        breadcrumb_items = [("Home", reverse("storefront:home"))]
        if context["category"] is not None:
            breadcrumb_items.append(
                (context["category"].name, context["category"].get_absolute_url())
            )
        else:
            breadcrumb_items.append(("All Products", reverse("storefront:product_list")))
        context["breadcrumb_jsonld"] = seo.breadcrumb_json_ld(
            request=self.request, items=breadcrumb_items
        )
        return context


class ProductDetailView(DetailView[Product]):
    """The variant selector (gate 3: price/availability/gallery update
    without a reload) is client-side Alpine, driven off ``variants_json`` —
    a single ``<select>`` over full variant labels ("Red / 50ml") rather
    than a per-attribute button grid, since a button grid only maps
    cleanly to one variant when a product varies along exactly one
    attribute dimension; a product varying along two (colour AND size)
    needs the combination, which a `<select>` sidesteps entirely by
    encoding each variant's full combination as one option.
    """

    model = Product
    template_name = "storefront/product_detail.html"
    context_object_name = "product"
    slug_url_kwarg = "slug"

    def get_queryset(self) -> QuerySet[Product]:
        return (
            Product.objects.filter(status=Product.Status.PUBLISHED)
            .select_related("brand", "category", "subcategory")
            .prefetch_related(
                "images",
                Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
                "variants__variant_attribute_values__value__definition",
            )
        )

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """§34: "old slugs 301-redirect." A slug that doesn't match any
        *current* published product falls back to ``ProductSlugRedirect``
        before giving up — resolved to ``product.slug`` at lookup time
        (see that model's own docstring for why an FK, not a snapshotted
        string, is what makes a twice-renamed product still resolve in
        one hop). A redirect to a product that isn't published anymore
        still 404s — a stale link shouldn't reveal that a draft/archived
        product exists.

        Every genuine 404 on this view — including one a scanner probing
        random slugs generates, not just a stale real link — now costs
        one extra query: a single indexed lookup on
        ``ProductSlugRedirect.old_slug`` (``unique=True`` already gives
        it the index; no join, no scan, bounded regardless of table
        size). Acceptable for a normal visitor's occasional typo, but
        this view has no rate limiting of its own — if 404 traffic here
        is ever heavy enough for that one extra query per request to
        matter, it needs the same treatment Stage 11 gave
        ``orders.tracking`` (also noted in specs/state.md), not a
        micro-optimisation of this lookup itself.
        """
        try:
            return super().get(request, *args, **kwargs)
        except Http404:
            redirect_row = (
                ProductSlugRedirect.objects.select_related("product")
                .filter(old_slug=self.kwargs["slug"])
                .first()
            )
            if redirect_row is not None and redirect_row.product.status == Product.Status.PUBLISHED:
                return HttpResponsePermanentRedirect(
                    reverse("storefront:product_detail", kwargs={"slug": redirect_row.product.slug})
                )
            raise

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        product = self.object
        variants = list(product.variants.all())
        default_variant = product.default_variant
        legacy_notes, description_without_legacy_notes = _split_legacy_fragrance_notes(
            product.description
        )
        context["display_top_notes"] = product.top_notes or legacy_notes.get("top", "")
        context["display_heart_notes"] = product.heart_notes or legacy_notes.get("heart", "")
        context["display_base_notes"] = product.base_notes or legacy_notes.get("base", "")
        context["display_description"] = description_without_legacy_notes
        context["concentration"] = (
            next(
                (
                    item.value.value
                    for item in default_variant.variant_attribute_values.all()
                    if item.value.definition.slug == "concentration"
                ),
                "",
            )
            if default_variant is not None
            else ""
        )
        images = list(product.images.all())
        primary_image = next((image for image in images if image.is_primary), None)

        context["gallery_images"] = [
            {
                "id": image.pk,
                "full": image.full_webp.url,
                "card": image.card_webp.url,
                "thumb": image.thumb_webp.url,
                "alt": image.alt_text or product.name,
            }
            for image in images
        ]
        context["default_variant"] = default_variant
        context["variant_options"] = [
            {"id": variant.pk, "label": variant.display_label} for variant in variants
        ]
        # A plain Python list, not a pre-serialized JSON string — the
        # template's json_script tag does its own serialization/escaping.
        # available_quantity is with_available_quantity()'s runtime
        # .annotate() field — django-stubs can't see it statically.
        context["variants_data"] = [
            {
                "id": variant.pk,
                "price": str(variant.price),
                # Pre-formatted so the price the customer sees matches the
                # cart and checkout ("Rs. 16,000.00", never "Rs. 16000.00").
                "price_display": money(variant.price),
                "available_quantity": variant.available_quantity,  # type: ignore[attr-defined]
            }
            for variant in variants
        ]
        if settings.PRODUCT_REVIEWS_ENABLED:
            review_summary = ProductReview.objects.filter(
                product=product, is_approved=True
            ).aggregate(average=Avg("rating"), count=Count("id"))
            context["reviews"] = ProductReview.objects.filter(
                product=product, is_approved=True
            ).order_by("-created_at")[:20]
            context["review_average"] = review_summary["average"]
            context["review_count"] = review_summary["count"]
            context["review_form"] = ProductReviewForm()

        trending_cutoff = timezone.now() - timedelta(days=TRENDING_WINDOW_DAYS)
        recent_sales = (
            OrderItem.objects.filter(
                variant__product_id=OuterRef("pk"),
                order__created_at__gte=trending_cutoff,
                order__status__in=(
                    Order.Status.CONFIRMED,
                    Order.Status.PROCESSING,
                    Order.Status.READY_TO_DISPATCH,
                    Order.Status.DISPATCHED,
                    Order.Status.OUT_FOR_DELIVERY,
                    Order.Status.DELIVERED,
                ),
            )
            .values("variant__product_id")
            .annotate(quantity_sold=Sum("quantity"))
            .values("quantity_sold")
        )
        recommendation_candidates: ProductQuerySet = (
            Product.objects.filter(status=Product.Status.PUBLISHED)
            .exclude(pk=product.pk)
            .select_related("brand", "category", "subcategory")
            .with_pricing()
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.filter(is_primary=True),
                    to_attr="primary_image_list",
                ),
                Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
            )
        )
        curated_trending = recommendation_candidates.filter(is_trending=True).order_by(
            "-updated_at", "name"
        )[:RELATED_PRODUCTS_LIMIT]
        curated_products = list(curated_trending)
        remaining_slots = RELATED_PRODUCTS_LIMIT - len(curated_products)
        automatic_trending: list[Product] = []
        if remaining_slots:
            automatic_trending = list(
                recommendation_candidates.exclude(
                    pk__in=[product.pk, *(item.pk for item in curated_products)]
                )
                .filter(Exists(recent_sales))
                .order_by(
                    Subquery(recent_sales, output_field=IntegerField()).desc(), "-created_at"
                )[:remaining_slots]
            )
        related_products = [*curated_products, *automatic_trending]
        remaining_slots = RELATED_PRODUCTS_LIMIT - len(related_products)
        if remaining_slots:
            related_filter = Q(category_id=product.category_id)
            if product.brand_id is not None:
                related_filter |= Q(brand_id=product.brand_id)
            same_category_or_brand = list(
                recommendation_candidates.exclude(
                    pk__in=[product.pk, *(item.pk for item in related_products)]
                )
                .filter(related_filter)
                .order_by("-created_at", "name")[:remaining_slots]
            )
            related_products.extend(same_category_or_brand)
            remaining_slots = RELATED_PRODUCTS_LIMIT - len(related_products)
        if remaining_slots:
            related_products.extend(
                recommendation_candidates.exclude(
                    pk__in=[product.pk, *(item.pk for item in related_products)]
                ).order_by("-created_at", "name")[:remaining_slots]
            )
        context["related_products"] = related_products
        _attach_json_ld(context["related_products"], request=self.request)

        context["primary_image_url"] = (
            self.request.build_absolute_uri(primary_image.full_webp.url)
            if primary_image is not None
            else ""
        )

        # §34: Product + BreadcrumbList JSON-LD. images/variants above are
        # already fully evaluated Python lists by this point — passing
        # primary_image explicitly (rather than letting product_json_ld()
        # reach into product.images.all() itself) is what keeps this
        # N+1-safe regardless of which prefetch shape a future caller uses.
        context["product_jsonld"] = seo.product_json_ld(
            product,
            request=self.request,
            primary_image=primary_image,
            currency=StoreSettings.load().currency,
        )
        breadcrumb_items = [("Home", reverse("storefront:home"))]
        if product.category is not None:
            breadcrumb_items.append((product.category.name, product.category.get_absolute_url()))
        breadcrumb_items.append((product.name, product.get_absolute_url()))
        context["breadcrumb_jsonld"] = seo.breadcrumb_json_ld(
            request=self.request, items=breadcrumb_items
        )
        return context


@method_decorator(sensitive_post_parameters("order_number", "mobile_number"), name="post")
class ProductReviewSubmitView(FormView[ProductReviewForm]):
    """Accept reviews only from the matching phone on a delivered order."""

    form_class = ProductReviewForm

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if not settings.PRODUCT_REVIEWS_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: ProductReviewForm) -> HttpResponse:
        ip_address = client_ip(self.request)
        try:
            check_rate_limit(
                scope=RateLimitScope.REVIEW,
                ip_address=ip_address,
                policy=PRODUCT_REVIEW_RATE_LIMIT,
            )
        except RateLimitedError:
            return HttpResponse("Too many review attempts. Please try again later.", status=429)

        product = get_object_or_404(
            Product, slug=self.kwargs["slug"], status=Product.Status.PUBLISHED
        )
        review = submit_product_review(
            product=product,
            order_number=form.cleaned_data["order_number"],
            mobile_number=form.cleaned_data["mobile_number"],
            rating=form.cleaned_data["rating"],
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
        )
        record_attempt(
            scope=RateLimitScope.REVIEW,
            ip_address=ip_address,
            succeeded=review is not None,
        )
        return HttpResponseRedirect(f"{product.get_absolute_url()}#reviews")

    def form_invalid(self, form: ProductReviewForm) -> HttpResponse:
        return HttpResponse(
            "Please provide a valid review and order verification details.", status=400
        )


HOME_SECTION_SIZE = 8
"""Featured and new-arrivals rails both cap at 8 — a 4-column desktop grid
divides evenly with no partial final row, same reasoning as
STOREFRONT_PAGE_SIZE."""

HOME_CATEGORY_LIMIT = 8
"""A live contrast/content audit of the redesigned home page found the
category grid rendering every published category (80 in the dev database,
a mix of real rows and leftover test fixtures) — over two-thirds of the
page's total height, mostly duplicate-looking empty tiles. Capped here,
not just visually truncated in the template: an un-rendered row costs
nothing, a rendered-then-hidden one still costs the query, the markup,
and the download."""


class BrandListView(ListView[Brand]):
    """List every published brand that has products available to browse."""

    model = Brand
    template_name = "storefront/brand_list.html"
    context_object_name = "brands"

    def get_queryset(self) -> QuerySet[Brand]:
        return (
            Brand.objects.filter(
                is_published=True,
                products__status=Product.Status.PUBLISHED,
            )
            .distinct()
            .order_by("name")
        )


class HomeView(ListView[Product]):
    """Featured products, new arrivals, and category tiles on the home page
    (roadmap Stage 6). The two rails deliberately aren't deduplicated
    against each other — "featured" and "newest" are independent
    curations, and a product can legitimately belong to both."""

    model = Product
    template_name = "storefront/home.html"
    context_object_name = "featured_products"

    @staticmethod
    def _with_primary_image(queryset: ProductQuerySet) -> ProductQuerySet:
        # Also prefetches variants (with_available_quantity(), the same
        # annotation the listing page uses) — needed for
        # Product.default_variant, which _attach_json_ld() below reads
        # per card. Added alongside Stage 12's JSON-LD work specifically
        # so both rails on this page get the same per-card structured
        # data the listing page does, not a silently inconsistent subset.
        return queryset.with_pricing().prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_primary=True),
                to_attr="primary_image_list",
            ),
            Prefetch("variants", queryset=ProductVariant.objects.with_available_quantity()),
        )

    def get_queryset(self) -> QuerySet[Product]:
        base: ProductQuerySet = Product.objects.filter(
            status=Product.Status.PUBLISHED, is_featured=True
        )
        return self._with_primary_image(base).order_by("-created_at")[:HOME_SECTION_SIZE]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        all_categories = Category.objects.filter(parent__isnull=True, is_published=True).order_by(
            "position", "name"
        )
        context["categories"] = list(all_categories[:HOME_CATEGORY_LIMIT])
        context["has_more_categories"] = all_categories.count() > HOME_CATEGORY_LIMIT
        context["brands"] = list(
            Brand.objects.filter(
                is_published=True,
                products__status=Product.Status.PUBLISHED,
            )
            .distinct()
            .order_by("name")[:HOME_BRANDS_LIMIT]
        )
        new_arrivals: ProductQuerySet = Product.objects.filter(status=Product.Status.PUBLISHED)
        context["featured_products"] = list(context["featured_products"])
        context["new_arrivals"] = list(
            self._with_primary_image(new_arrivals).order_by("-created_at")[:HOME_SECTION_SIZE]
        )
        _attach_json_ld(context["featured_products"], request=self.request)
        _attach_json_ld(context["new_arrivals"], request=self.request)
        return context
