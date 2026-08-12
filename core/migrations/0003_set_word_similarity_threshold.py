"""Sets pg_trgm.word_similarity_threshold explicitly, database-wide.

CLAUDE.md's Traps section (search) and requirements §15.2 are both explicit
on this: "Do not rely on the default word_similarity_threshold. Set it in a
migration so CI and production agree." Postgres's own compiled-in default
(0.6) happens to already be the value ``search/backends.py`` was verified
against — see ``core.config.PG_TRGM_WORD_SIMILARITY_THRESHOLD`` for the
cases that pin it down (the ``afnn``/``Afnan`` typo, and a partial SKU
inside a longer one). This migration exists so that value is a checked-in
decision, not an unverified assumption riding on whatever a given Postgres
install ships with — a future Postgres version changing its compiled-in
default would silently change matching behaviour without this.

``ALTER DATABASE ... SET`` only takes effect for *new* connections/sessions
opened after it runs, not the one currently applying the migration — this
is a `SET ... FOR DATABASE`-style default, not a live `SET` on the current
session. Fine for this project (one process, reconnects normally), but
worth knowing if a test using the same connection the migration ran on
expects to observe it immediately without a fresh connection.
"""

from __future__ import annotations

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

from core.config import PG_TRGM_WORD_SIMILARITY_THRESHOLD


def set_threshold(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    db_name = schema_editor.connection.settings_dict["NAME"]
    quoted_db_name = schema_editor.connection.ops.quote_name(db_name)
    schema_editor.execute(
        f"ALTER DATABASE {quoted_db_name} "
        f"SET pg_trgm.word_similarity_threshold = {PG_TRGM_WORD_SIMILARITY_THRESHOLD}"
    )


def reset_threshold(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    db_name = schema_editor.connection.settings_dict["NAME"]
    quoted_db_name = schema_editor.connection.ops.quote_name(db_name)
    schema_editor.execute(f"ALTER DATABASE {quoted_db_name} RESET pg_trgm.word_similarity_threshold")


class Migration(migrations.Migration):
    dependencies = [("core", "0002_create_cache_table")]

    operations = [
        migrations.RunPython(set_threshold, reset_threshold),
    ]
