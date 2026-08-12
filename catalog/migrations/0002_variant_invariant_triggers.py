"""Deferred DB-level backstop for "every product has >=1 variant".

catalog.services.create_product() is the primary mechanism (creates the
product and its default variant in one transaction). These two Postgres
CONSTRAINT TRIGGERs are the backstop for anything that bypasses it — a
Django admin save, a raw script, a future CSV import — and they use
DEFERRABLE INITIALLY DEFERRED specifically so the check runs once at
transaction COMMIT rather than after each individual INSERT/DELETE
statement. Without that, the ordinary "create the product row, then create
its variant row" sequence — which necessarily leaves the product briefly
variant-less between those two statements — would fail on the first
statement, which is exactly the invariant we want, just not that early.
"""

from __future__ import annotations

from django.db import migrations

CREATE_PRODUCT_CHECK_FUNCTION = """
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

CREATE_PRODUCT_TRIGGER = """
CREATE CONSTRAINT TRIGGER product_must_have_variant
AFTER INSERT ON catalog_product
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog_product_must_have_variant();
"""

CREATE_VARIANT_DELETE_CHECK_FUNCTION = """
CREATE OR REPLACE FUNCTION catalog_variant_delete_leaves_product_with_variant()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM catalog_product WHERE id = OLD.product_id)
       AND NOT EXISTS (
            SELECT 1 FROM catalog_productvariant WHERE product_id = OLD.product_id
       ) THEN
        RAISE EXCEPTION 'Product id=% must retain at least one variant', OLD.product_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

CREATE_VARIANT_DELETE_TRIGGER = """
CREATE CONSTRAINT TRIGGER variant_delete_leaves_product_with_variant
AFTER DELETE ON catalog_productvariant
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION catalog_variant_delete_leaves_product_with_variant();
"""

DROP_ALL = """
DROP TRIGGER IF EXISTS product_must_have_variant ON catalog_product;
DROP TRIGGER IF EXISTS variant_delete_leaves_product_with_variant ON catalog_productvariant;
DROP FUNCTION IF EXISTS catalog_product_must_have_variant();
DROP FUNCTION IF EXISTS catalog_variant_delete_leaves_product_with_variant();
"""


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=(
                CREATE_PRODUCT_CHECK_FUNCTION
                + CREATE_PRODUCT_TRIGGER
                + CREATE_VARIANT_DELETE_CHECK_FUNCTION
                + CREATE_VARIANT_DELETE_TRIGGER
            ),
            reverse_sql=DROP_ALL,
        ),
    ]
