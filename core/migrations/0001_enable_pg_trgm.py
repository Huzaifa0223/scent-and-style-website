"""Enable pg_trgm now, not at Stage 5.

Search (Stage 5) needs trigram indexes, but this runs in Stage 1 so the test
database — built from a plain ``migrate`` — has the extension from the very
first `migrate`, matching CLAUDE.md's "traps" note on this exact point.
"""

from __future__ import annotations

from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        CreateExtension("pg_trgm"),
    ]
