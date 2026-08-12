"""Create the database cache table as a migration, not a manual step.

``createcachetable`` is a management command, not a migration operation. If
this table only existed because someone remembered to run that command by
hand, the pytest-django test database — built purely by replaying
migrations — would never have it, and StoreSettings' cache-invalidation
gate would error instead of failing meaningfully. Running the command from
inside a migration gives dev, test, and CI databases the table identically,
with zero manual steps.
"""

from __future__ import annotations

from typing import Any

from django.core.management import call_command
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps


def create_cache_table(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    call_command("createcachetable")


def drop_cache_table(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    schema_editor.execute("DROP TABLE IF EXISTS django_cache_table")


class Migration(migrations.Migration):
    dependencies = [("core", "0001_enable_pg_trgm")]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
