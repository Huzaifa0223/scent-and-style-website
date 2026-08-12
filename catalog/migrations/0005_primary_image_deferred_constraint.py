"""Replaces the "at most one primary image per product" invariant.

The fourth instance of the same wall as migrations 0003 and 0004:
``productimage_one_primary_per_product`` was a partial ``UniqueConstraint``
(``condition=Q(is_primary=True)``), immediate because Postgres/Django forbid
combining a unique constraint's ``condition`` with ``deferrable=True``. That
forces every primary-image swap into a specific unset-then-set statement
order, and the portal's image-management form (reorder + re-primary +
delete, all in one submit) can't guarantee that order any more than the
variant formset could for the default variant. Same fix, same reasoning:
a deferred ``CONSTRAINT TRIGGER``, checked once at COMMIT.
"""

from __future__ import annotations

from django.db import migrations

CREATE_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_image_at_most_one_primary() RETURNS trigger AS $$
BEGIN
    IF (
        SELECT COUNT(*) FROM catalog_productimage
        WHERE product_id = NEW.product_id AND is_primary = TRUE
    ) > 1 THEN
        RAISE EXCEPTION 'Product id=% may have at most one primary image', NEW.product_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE CONSTRAINT TRIGGER image_at_most_one_primary
AFTER INSERT OR UPDATE OF is_primary ON catalog_productimage
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW WHEN (NEW.is_primary)
EXECUTE FUNCTION catalog_image_at_most_one_primary();
"""

DROP_ALL = """
DROP TRIGGER IF EXISTS image_at_most_one_primary ON catalog_productimage;
DROP FUNCTION IF EXISTS catalog_image_at_most_one_primary();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_variant_attribute_signature_deferred_constraint"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="productimage",
            name="productimage_one_primary_per_product",
        ),
        migrations.RunSQL(sql=CREATE_CHECK_FUNCTION + CREATE_TRIGGER, reverse_sql=DROP_ALL),
    ]
