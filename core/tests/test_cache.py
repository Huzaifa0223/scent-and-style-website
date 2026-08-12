from __future__ import annotations

import pytest
from django.core.cache import cache


@pytest.mark.django_db
def test_database_cache_actually_persists_not_a_silent_noop() -> None:
    """Proves core.migrations.0002_create_cache_table really created the
    table the DatabaseCache backend needs — a missing table would make
    cache.set/get silently fail in a way StoreSettings' cache tests alone
    would not distinguish from working correctly."""
    cache.delete("cache-smoke-test")
    assert cache.get("cache-smoke-test") is None

    cache.set("cache-smoke-test", "value", timeout=None)
    assert cache.get("cache-smoke-test") == "value"

    cache.delete("cache-smoke-test")
    assert cache.get("cache-smoke-test") is None
