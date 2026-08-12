"""The Staff group's existence and permission set — including the
flush-survival path that migration 0001 alone doesn't cover (see
accounts/apps.py's module docstring for the full diagnosis: a
``transaction=True`` test's teardown calls Django's ``flush``, which
truncates every table including ``auth_group`` and then re-fires
``post_migrate`` to restore baseline data; without accounts/apps.py's
``post_migrate`` receiver — and without accounts/models.py existing at all,
so the signal isn't skipped for this app — that flush would silently wipe
the Staff group with nothing to recreate it).
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from accounts.permissions import staff_permissions


def _assert_staff_group_is_correct() -> None:
    group = Group.objects.get(name="Staff")
    actual = set(group.permissions.values_list("codename", "content_type__app_label"))
    expected = set(
        staff_permissions(Permission.objects.all()).values_list(
            "codename", "content_type__app_label"
        )
    )
    assert actual == expected
    assert actual, "expected the Staff group to hold at least one permission"


@pytest.mark.django_db
def test_staff_group_holds_exactly_the_expected_permissions() -> None:
    _assert_staff_group_is_correct()


@pytest.mark.django_db(transaction=True)
def test_staff_group_survives_a_flush() -> None:
    """Explicitly flushes (rather than relying on this test's own teardown,
    which happens after the assertion and so wouldn't prove anything about
    *this* test) to directly exercise the exact mechanism migration 0001's
    docstring and accounts/apps.py's post_migrate receiver describe."""
    call_command("flush", verbosity=0, interactive=False)

    _assert_staff_group_is_correct()
