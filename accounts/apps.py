"""Also see accounts/migrations/0001_create_staff_group.py.

The migration seeds the "Staff" group once, at first migrate. But Django's
``flush`` command (which ``TransactionTestCase``/``@pytest.mark.django_db
(transaction=True)`` runs as teardown, and which a real deploy might run
too) truncates every table and then re-fires ``post_migrate`` to restore
baseline data — that restores Django's own default Permissions
(``create_permissions`` is itself a ``post_migrate`` receiver) but *not*
anything a migration's ``RunPython`` did, since that's not signal-driven.
Confirmed empirically: running any ``transaction=True`` test silently wiped
the Staff group for the rest of that database's life, with nothing to
recreate it — a real, load-bearing bug, not a hypothetical one.

The fix is to make group membership self-healing: reassert it on every
``post_migrate`` for this app, not just at first migrate. ``post_migrate``
fires after both a normal ``migrate`` *and* a ``flush``, which is exactly
the coverage the one-time migration was missing.

The "which permissions" criteria itself lives in accounts/permissions.py,
shared with the migration — see that module's docstring for why sharing it
is safe despite migrations normally avoiding application-code imports.

Open question (recorded in full in specs/state.md): reasserting the exact
same permission set on every post_migrate also means it *reverts* any
manual permission change made through /django-admin/auth/group/ — e.g. if
the Owner manually grants Staff a permission outside this list, the next
migrate or flush silently takes it back. Acceptable for Stage 3 (nobody has
a reason to hand-edit this group yet); Stage 17 replaces this blunt
sync-to-fixed-set behavior with real granular permission management, and
needs to account for it.
"""

from __future__ import annotations

from typing import Any

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self) -> None:
        post_migrate.connect(_sync_staff_group, sender=self)


def _sync_staff_group(sender: AppConfig, **kwargs: Any) -> None:
    # Real (non-historical) models — this runs as a signal receiver, not a
    # migration operation, so there's no need for apps.get_model() here.
    from django.contrib.auth.models import Group, Permission

    from accounts.permissions import STAFF_GROUP_NAME, staff_permissions

    group, _ = Group.objects.get_or_create(name=STAFF_GROUP_NAME)
    group.permissions.set(staff_permissions(Permission.objects.all()))
