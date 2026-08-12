from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from .models import StoreSettings


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin[StoreSettings]):
    """Singleton admin: no Add, no Delete — there is exactly one row, ever."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: StoreSettings | None = None) -> bool:
        return False
