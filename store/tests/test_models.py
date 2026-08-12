from __future__ import annotations

import pytest
from django.core.cache import cache
from django.db import IntegrityError, transaction

from core.config import STORE_SETTINGS_CACHE_KEY
from store.models import StoreSettings


@pytest.mark.django_db
def test_load_creates_singleton_with_defaults_on_first_call() -> None:
    assert StoreSettings.objects.count() == 0
    settings_obj = StoreSettings.load()
    assert settings_obj.pk == 1
    assert settings_obj.currency == "PKR"
    assert settings_obj.timezone == "Asia/Karachi"
    assert StoreSettings.objects.count() == 1


@pytest.mark.django_db
def test_load_is_cached_and_skips_the_get_or_create_query(django_assert_num_queries) -> None:
    StoreSettings.load()
    # CACHES uses the database backend, so a cache hit still costs one query
    # against django_cache_table — the win is skipping StoreSettings'
    # get_or_create round trip, not reaching zero queries.
    with django_assert_num_queries(1):
        StoreSettings.load()


@pytest.mark.django_db
def test_save_pins_primary_key_to_one_even_if_changed() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.pk = 99
    settings_obj.save()
    assert settings_obj.pk == 1
    assert StoreSettings.objects.count() == 1


@pytest.mark.django_db
def test_second_row_violates_singleton_check_constraint() -> None:
    StoreSettings.load()
    with pytest.raises(IntegrityError), transaction.atomic():
        StoreSettings.objects.bulk_create([StoreSettings(pk=2, name="Rogue")])
    # the failed transaction must not have left a second row behind
    assert StoreSettings.objects.count() == 1


@pytest.mark.django_db
def test_save_invalidates_cache_so_next_load_reflects_the_edit() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.name = "New Name"
    settings_obj.save()

    reloaded = StoreSettings.load()
    assert reloaded.name == "New Name"


@pytest.mark.django_db
def test_delete_invalidates_cache() -> None:
    StoreSettings.load()
    assert cache.get(STORE_SETTINGS_CACHE_KEY) is not None

    StoreSettings.objects.get(pk=1).delete()
    assert cache.get(STORE_SETTINGS_CACHE_KEY) is None


@pytest.mark.django_db
def test_str_returns_store_name() -> None:
    settings_obj = StoreSettings.load()
    settings_obj.name = "Acme Store"
    settings_obj.save()
    assert str(settings_obj) == "Acme Store"
