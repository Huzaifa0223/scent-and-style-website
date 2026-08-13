"""order_number_seq (§22) — a real Postgres sequence, not an AutoField,
so order_number generation is decoupled from any table's own row ids and
nextval() stays non-transactional (never rolled back, never repeated
across concurrent transactions). See orders/order_number.py.
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE SEQUENCE order_number_seq START WITH 10000;",
            reverse_sql="DROP SEQUENCE order_number_seq;",
        ),
    ]
