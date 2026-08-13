from __future__ import annotations

from django.contrib import admin

from .models import DeliveryZone


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin[DeliveryZone]):
    list_display = ("city", "charge")
    search_fields = ("city",)
    ordering = ("city",)
