"""Product.save()'s slug-change -> ProductSlugRedirect capture (§34,
roadmap Stage 12). The redirect *view*'s own behaviour (301 for a
matched old slug, 404 for an unpublished target) lives in
storefront/tests/test_product_detail_view.py — this file covers only the
model-level invariant: a slug change on an existing product always
leaves a usable trail behind.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from catalog import services as catalog_services
from catalog.factories import ProductFactory
from catalog.models import ProductSlugRedirect


@pytest.mark.django_db
def test_changing_the_slug_on_an_existing_product_records_a_redirect() -> None:
    product = ProductFactory(name="Original Name")
    original_slug = product.slug

    product.slug = "a-brand-new-slug"
    product.save()

    redirect = ProductSlugRedirect.objects.get(old_slug=original_slug)
    assert redirect.product_id == product.pk


@pytest.mark.django_db
def test_a_max_length_slug_round_trips_into_the_redirect_without_truncation_or_error() -> None:
    """ProductSlugRedirect.old_slug is max_length=220 specifically to
    match Product.slug's own max_length exactly — a mismatch would
    silently truncate (or raise) a capture for a product whose slug is
    long enough to hit the difference. Exercises the actual boundary,
    not just a code-reading claim that the two numbers agree."""
    product = ProductFactory(name="Original Name")
    max_length_slug = "x" * 220
    product.slug = max_length_slug
    product.save()

    product.slug = "short-slug"
    product.save()

    redirect = ProductSlugRedirect.objects.get(old_slug=max_length_slug)
    assert len(redirect.old_slug) == 220
    assert redirect.old_slug == max_length_slug


@pytest.mark.django_db
def test_creating_a_product_writes_no_redirect() -> None:
    ProductFactory(name="Fresh Product")

    assert ProductSlugRedirect.objects.count() == 0


@pytest.mark.django_db
def test_saving_a_product_without_changing_the_slug_writes_no_redirect() -> None:
    product = ProductFactory(name="Untouched Product")

    product.short_description = "Just editing something else."
    product.save()

    assert ProductSlugRedirect.objects.count() == 0


@pytest.mark.django_db
def test_a_twice_renamed_products_first_slug_resolves_to_the_current_one_in_one_hop() -> None:
    """The redirect is an FK to the live product, not a snapshotted
    string — renaming twice must not require updating the first
    redirect's target; it should already resolve correctly because
    product.slug is read live at lookup time."""
    product = ProductFactory(name="Original Name")
    first_slug = product.slug

    product.slug = "second-slug"
    product.save()
    product.slug = "third-slug"
    product.save()

    redirect = ProductSlugRedirect.objects.get(old_slug=first_slug)
    assert redirect.product.slug == "third-slug"
    # The intermediate slug also redirects to the same, current product.
    intermediate_redirect = ProductSlugRedirect.objects.get(old_slug="second-slug")
    assert intermediate_redirect.product.slug == "third-slug"


@pytest.mark.django_db
def test_clearing_the_slug_to_force_regeneration_also_records_a_redirect() -> None:
    product = ProductFactory(name="Original Name")
    original_slug = product.slug

    product.slug = ""
    product.name = "Completely Different Name"
    product.save()

    assert product.slug != original_slug
    redirect = ProductSlugRedirect.objects.get(old_slug=original_slug)
    assert redirect.product_id == product.pk


@pytest.mark.django_db
def test_repeated_identical_slug_change_is_idempotent() -> None:
    """get_or_create() means resaving with the same already-changed slug
    (e.g. a merchant resubmitting the edit form) doesn't raise on the
    redirect's own unique constraint."""
    product = ProductFactory(name="Original Name")
    original_slug = product.slug
    product.slug = "new-slug"
    product.save()

    product.short_description = "A harmless second edit."
    product.save()  # must not raise — slug hasn't changed since the last save

    assert ProductSlugRedirect.objects.filter(old_slug=original_slug).count() == 1


@pytest.mark.django_db
def test_auto_generated_slug_avoids_an_existing_redirect_target() -> None:
    """A brand-new product must never be silently auto-assigned a slug
    that's already promised to redirect to a *different* product."""
    renamed = ProductFactory(name="Wireless Mouse")
    original_slug = renamed.slug
    renamed.slug = "wireless-mouse-v2"
    renamed.save()
    assert ProductSlugRedirect.objects.filter(old_slug=original_slug).exists()

    # Same source name as the original product, so unique_slugify() would
    # naturally collide with the just-vacated original_slug if it didn't
    # also check the redirect table.
    new_product = catalog_services.create_product(
        name="Wireless Mouse",
        category=renamed.category,
        default_variant_price=Decimal("10.00"),
    )

    assert new_product.slug != original_slug
    assert not ProductSlugRedirect.objects.filter(old_slug=new_product.slug).exists()
