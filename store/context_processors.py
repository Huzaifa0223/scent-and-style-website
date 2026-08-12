from __future__ import annotations

from django.http import HttpRequest

from .models import StoreSettings


def store_settings(request: HttpRequest) -> dict[str, StoreSettings]:
    """Expose the singleton StoreSettings row to every template render."""
    return {"store_settings": StoreSettings.load()}
