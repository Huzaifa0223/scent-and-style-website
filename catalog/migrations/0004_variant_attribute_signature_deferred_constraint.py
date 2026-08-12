"""Replaces the "unique attribute set per product" invariant.

It was a plain partial UniqueConstraint (``condition=~Q(attribute_signature="")``).
Same restriction as migration 0003: Postgres/Django forbid combining a
unique constraint's ``condition`` with ``deferrable=True``, so the partial
index was immediate — checked after every individual UPDATE, not once at
COMMIT. That breaks two legal edits Stage 3's variant formset needs to
support in a single transaction: swapping two variants' attribute sets
(50ml <-> 100ml passes ``clean()``, since the submitted sets are distinct,
but raises IntegrityError when the first variant's saved
``attribute_signature`` briefly equals what the second variant still
holds), and deleting one variant while reassigning its attributes to a
survivor (same transient-duplicate shape). This is the third invariant on
this model to hit the same wall — see migrations 0002 and 0003 — so the
fix is the same: a deferred constraint trigger, checked once at COMMIT.
"""

from __future__ import annotations

from django.db import migrations

CREATE_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_variant_unique_attribute_set_per_product() RETURNS trigger AS $$
BEGIN
    IF (
        SELECT COUNT(*) FROM catalog_productvariant
        WHERE product_id = NEW.product_id AND attribute_signature = NEW.attribute_signature
    ) > 1 THEN
        RAISE EXCEPTION
            'Product id=% has more than one variant with attribute set "%"',
            NEW.product_id, NEW.attribute_signature
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_TRIGGER = """
CREATE CONSTRAINT TRIGGER variant_unique_attribute_set_per_product
AFTER INSERT OR UPDATE OF attribute_signature ON catalog_productvariant
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW WHEN (NEW.attribute_signature <> '')
EXECUTE FUNCTION catalog_variant_unique_attribute_set_per_product();
"""

DROP_ALL = """
DROP TRIGGER IF EXISTS variant_unique_attribute_set_per_product ON catalog_productvariant;
DROP FUNCTION IF EXISTS catalog_variant_unique_attribute_set_per_product();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_default_variant_deferred_constraint"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="productvariant",
            name="variant_unique_attribute_set_per_product",
        ),
        migrations.RunSQL(sql=CREATE_CHECK_FUNCTION + CREATE_TRIGGER, reverse_sql=DROP_ALL),
    ]
