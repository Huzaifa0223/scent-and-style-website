from __future__ import annotations

import pytest
from django.template import engines

from store.context_processors import store_settings as store_settings_processor
from store.models import StoreSettings


@pytest.mark.django_db
def test_context_processor_returns_the_singleton(rf) -> None:
    request = rf.get("/")
    context = store_settings_processor(request)
    assert isinstance(context["store_settings"], StoreSettings)
    assert context["store_settings"].pk == 1


@pytest.mark.django_db
def test_editing_a_store_setting_is_reflected_in_the_next_template_render(rf) -> None:
    """Acceptance gate 4: an edit must show up on the *next* render, proving
    the cache is invalidated rather than serving a stale singleton for its
    full TTL."""
    settings_obj = StoreSettings.load()
    request = rf.get("/")
    template = engines["django"].from_string("{{ store_settings.name }}")

    assert template.render({}, request) == "My Store"

    settings_obj.name = "Renamed Store"
    settings_obj.save()

    assert template.render({}, request) == "Renamed Store"
