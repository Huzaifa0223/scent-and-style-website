"""Product quick actions (Stage 3): publish, unpublish, feature, unfeature,
archive. Each is its own POST-only endpoint (portal/product_actions.py),
same shape as the image management split — verified here the same way:
GET is rejected, a user without catalog.change_product is blocked (403),
and each action changes exactly the one field it owns.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages

from catalog.factories import ProductFactory
from catalog.models import Product

_ACTION_URLS = [
    "publish",
    "unpublish",
    "archive",
    "feature",
    "unfeature",
]


def _login_owner(client, django_user_model):  # type: ignore[no-untyped-def]
    owner = django_user_model.objects.create_superuser(
        username="owner", email="o@example.com", password="x"
    )
    client.force_login(owner)
    return owner


def _url(action: str, pk: int) -> str:
    return f"/admin-portal/products/{pk}/{action}/"


@pytest.mark.django_db
def test_publish_sets_status_to_published(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.DRAFT)

    response = client.post(_url("publish", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.status == Product.Status.PUBLISHED


@pytest.mark.django_db
def test_publish_from_archived_reverses_the_archive(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """There is no dedicated "unarchive" action — publish already covers
    archived -> published, per the roadmap's five-action list."""
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.ARCHIVED)

    response = client.post(_url("publish", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.status == Product.Status.PUBLISHED


@pytest.mark.django_db
def test_unpublish_sets_status_to_draft(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.PUBLISHED)

    response = client.post(_url("unpublish", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.status == Product.Status.DRAFT


@pytest.mark.django_db
def test_archive_sets_status_to_archived_and_does_not_touch_variants(
    client, django_user_model
) -> None:  # type: ignore[no-untyped-def]
    """Archive is a pure status transition — the product's variants must
    stay exactly as they were (still active, still with their stock), per
    the decision recorded in product_actions.py and specs/state.md: nothing
    downstream should ever have to distinguish "archived" from a silent
    partial delete."""
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.PUBLISHED)
    variant = product.variants.get()
    assert variant.is_active is True
    original_stock_quantity = variant.stock_quantity

    response = client.post(_url("archive", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    variant.refresh_from_db()
    assert product.status == Product.Status.ARCHIVED
    assert variant.is_active is True
    assert variant.stock_quantity == original_stock_quantity


@pytest.mark.django_db
def test_feature_sets_is_featured_true(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(is_featured=False)

    response = client.post(_url("feature", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.is_featured is True


@pytest.mark.django_db
def test_unfeature_sets_is_featured_false(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(is_featured=True)

    response = client.post(_url("unfeature", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.is_featured is False


@pytest.mark.django_db
def test_archive_leaves_is_featured_untouched(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """Archiving a featured product does not silently unfeature it — that's
    a separate, independent action a merchant fires deliberately."""
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.PUBLISHED, is_featured=True)

    response = client.post(_url("archive", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.status == Product.Status.ARCHIVED
    assert product.is_featured is True


@pytest.mark.django_db
def test_publish_shows_a_success_message(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory(status=Product.Status.DRAFT)

    response = client.post(_url("publish", product.pk), follow=True)

    levels = [message.level_tag for message in get_messages(response.wsgi_request)]
    assert levels == ["success"]


@pytest.mark.parametrize("action", _ACTION_URLS)
@pytest.mark.django_db
def test_action_is_post_only(client, django_user_model, action: str) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    product = ProductFactory()

    response = client.get(_url(action, product.pk))

    assert response.status_code == 405


@pytest.mark.parametrize("action", _ACTION_URLS)
@pytest.mark.django_db
def test_action_requires_change_product_permission(client, django_user_model, action: str) -> None:  # type: ignore[no-untyped-def]
    """A user with no catalog permissions at all — not the seeded Staff
    group, which does hold change_product — must be blocked."""
    powerless = django_user_model.objects.create_user(
        username="powerless", password="x", is_staff=True
    )
    client.force_login(powerless)
    product = ProductFactory()
    original_status = product.status
    original_is_featured = product.is_featured

    response = client.post(_url(action, product.pk))

    assert response.status_code == 403
    product.refresh_from_db()
    assert product.status == original_status
    assert product.is_featured == original_is_featured


@pytest.mark.django_db
def test_staff_group_can_publish_a_product(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    """The seeded Staff group holds catalog.change_product (add/change,
    never delete — accounts/permissions.py) — these actions are a change,
    not a delete, so Staff can use them."""
    staff = django_user_model.objects.create_user(username="staffer", password="x", is_staff=True)
    staff.groups.add(Group.objects.get(name="Staff"))
    client.force_login(staff)
    product = ProductFactory(status=Product.Status.DRAFT)

    response = client.post(_url("publish", product.pk))

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.status == Product.Status.PUBLISHED


@pytest.mark.django_db
def test_publish_action_appears_on_the_product_list(client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    _login_owner(client, django_user_model)
    ProductFactory(name="Draft Product", status=Product.Status.DRAFT)

    response = client.get("/admin-portal/products/")

    assert response.status_code == 200
    assert b"Publish" in response.content
