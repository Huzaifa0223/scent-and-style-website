"""Replaces the "at most one default variant per product" invariant.

It was a plain partial UniqueConstraint (``condition=Q(is_default=True)``).
Postgres/Django forbid combining a unique constraint's ``condition`` with
``deferrable=True`` — see ``UniqueConstraint with conditions cannot be
deferred`` — so an immediate partial index was the only way to express this
as a constraint, and it forces every default-variant swap into a specific
unset-then-set statement order to avoid a transient two-defaults state.
Stage 3's variant formset can't guarantee that order (form-save order isn't
"old default first"), so this switches to the same mechanism as migration
0002: a deferred constraint trigger, checked once at COMMIT rather than
after each individual UPDATE.
"""

from __future__ import annotations

from django.db import migrations

CREATE_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_variant_at_most_one_default() RETURNS trigger AS $$
BEGIN
    IF (
        SELECT COUNT(*) FROM catalog_productvariant
        WHERE product_id = NEW.product_id AND is_default = TRUE
    ) > 1 THEN
        RAISE EXCEPTION 'Product id=% may have at most one default variant', NEW.product_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE CONSTRAINT TRIGGER variant_at_most_one_default
AFTER INSERT OR UPDATE OF is_default ON catalog_productvariant
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW WHEN (NEW.is_default)
EXECUTE FUNCTION catalog_variant_at_most_one_default();
"""

DROP_ALL = """
DROP TRIGGER IF EXISTS variant_at_most_one_default ON catalog_productvariant;
DROP FUNCTION IF EXISTS catalog_variant_at_most_one_default();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0002_variant_invariant_triggers"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="productvariant",
            name="variant_one_default_per_product",
        ),
        migrations.RunSQL(sql=CREATE_CHECK_FUNCTION + CREATE_TRIGGER, reverse_sql=DROP_ALL),
    ]
