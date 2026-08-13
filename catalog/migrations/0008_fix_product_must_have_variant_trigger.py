"""Fixes a real, latent bug in ``catalog_product_must_have_variant()``
(migration 0002), found while Stage 8 gate 1's snapshot test created a
product and fully deleted it (product row and its variant both) within
one transaction — the exact shape of "create then immediately delete a
product" that no prior stage's test had exercised in a single
transaction.

The trigger's check function queried
``EXISTS (SELECT 1 FROM catalog_productvariant WHERE product_id =
NEW.id)`` unconditionally, with no guard for "does the product itself
still exist by the time this deferred trigger actually fires". A
product created and then fully deleted in the same transaction leaves
this deferred obligation queued from the original INSERT; by commit
time the product row is gone too, but the trigger still fired and
incorrectly raised "must have at least one variant" for a product that
no longer exists at all — there is nothing left to enforce the
invariant on. ``catalog_variant_delete_leaves_product_with_variant``
(the DELETE-side sibling trigger, same migration 0002) already had this
exact guard (``IF EXISTS (SELECT 1 FROM catalog_product WHERE id =
OLD.product_id) AND ...``); this migration brings the INSERT-side
trigger in line with it.

Unlikely to matter in real production usage (creating and fully
deleting the same product in one request is rare), but it is a real gap
in an invariant this project treats as load-bearing everywhere else, so
it's fixed rather than worked around in the test that found it.
"""

from __future__ import annotations

from django.db import migrations

FIX_PRODUCT_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_product_must_have_variant() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM catalog_product WHERE id = NEW.id)
       AND NOT EXISTS (
            SELECT 1 FROM catalog_productvariant WHERE product_id = NEW.id
       ) THEN
        RAISE EXCEPTION 'Product "%" (id=%) must have at least one variant', NEW.name, NEW.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

REVERT_PRODUCT_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_product_must_have_variant() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM catalog_productvariant WHERE product_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'Product "%" (id=%) must have at least one variant', NEW.name, NEW.id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_search_indexes_fastupdate_off")]

    operations = [
        migrations.RunSQL(
            sql=FIX_PRODUCT_CHECK_FUNCTION,
            reverse_sql=REVERT_PRODUCT_CHECK_FUNCTION,
        ),
    ]
