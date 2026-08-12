"""Creates the "Staff" Django Group with view/add/change (never delete)
permissions on every catalog model.

Without this, Stage 3's "staff blocked from store settings and user
management" gate is vacuous — a staff user with *zero* permissions is
blocked from literally everything, including the portal's own product list,
which proves nothing about permission discrimination. A real Staff group
that can do catalog work but not store settings or user management is what
actually exercises ``accounts.mixins.PortalPermissionRequiredMixin``.

Scoping the group to catalog only (not the fuller orders/inventory/
customers scope from requirements §32) is deliberate for this stage —
those apps don't have portal views yet. Stage 17 ("staff role and granular
permissions", roadmap) extends this same group's permissions once they do;
it does not need to create a new group.

Django creates each app's default ``add``/``change``/``delete``/``view``
Permission rows via the ``post_migrate`` signal — which fires once, only
after *every* migration in the current run has already applied. A data
migration runs *during* that sequence, so on a brand-new database (a fresh
clone, or CI's Postgres container) catalog's Permission rows don't exist
yet at this point — ``Permission.objects.filter(content_type__app_label=
"catalog")`` would silently return nothing, and the Staff group would end
up with zero permissions. ``create_staff_group`` below forces catalog's
permissions to exist first, exactly as ``post_migrate`` would have,
using Django's own ``create_permissions`` against the real (non-historical)
app registry, since it needs live model classes to introspect.

This migration is the mechanism for "the group exists the moment migrate
finishes" — but it is *not* sufficient on its own: ``manage.py flush``
(which pytest-django's ``transaction=True`` tests run as teardown, and
which a real deploy might run too) truncates every table and re-fires
``post_migrate`` to restore baseline data. That restores Django's default
Permissions but not this migration's group, since ``RunPython`` isn't
signal-driven. ``accounts/apps.py``'s ``post_migrate`` receiver is the
backstop that makes this self-healing after a flush too — same
primary-mechanism-plus-backstop shape as ``catalog.services.create_product``
plus its deferred constraint trigger.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps as global_apps
from django.apps.registry import Apps
from django.contrib.auth.management import create_permissions
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from accounts.permissions import STAFF_GROUP_NAME, staff_permissions


def create_staff_group(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    create_permissions(
        global_apps.get_app_config("catalog"),
        verbosity=0,
        using=schema_editor.connection.alias,
    )

    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")

    group, _ = group_model.objects.get_or_create(name=STAFF_GROUP_NAME)
    group.permissions.set(staff_permissions(permission_model.objects.all()))


def remove_staff_group(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    group_model = apps.get_model("auth", "Group")
    group_model.objects.filter(name=STAFF_GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies: list[Any] = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("catalog", "0003_default_variant_deferred_constraint"),
    ]

    operations = [
        migrations.RunPython(create_staff_group, remove_staff_group),
    ]
