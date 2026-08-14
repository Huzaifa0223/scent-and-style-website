"""Checkout form (§20) — single page, no multi-step wizard. A plain
``Form``, not a ``ModelForm``: its fields span ``Customer`` and ``Order``
data that doesn't correspond to any one model 1:1 (customer contact
details, delivery details, and free-text notes all live on ``Order`` as
snapshots, while ``Customer`` only ever gets touched via
``customers.services.get_or_create_customer()``).
"""

from __future__ import annotations

from typing import Any

from django import forms

from core.forms import AriaDescribedByMixin, StorefrontStyledFieldMixin
from core.phone import normalize_pk_mobile


class CheckoutForm(AriaDescribedByMixin, StorefrontStyledFieldMixin, forms.Form):
    name = forms.CharField(max_length=200)
    mobile_number = forms.CharField(max_length=20, label="Mobile number")
    same_as_mobile = forms.BooleanField(required=False, initial=True, label="Same as mobile")
    whatsapp_number = forms.CharField(max_length=20, required=False, label="WhatsApp number")
    email = forms.EmailField(required=False)
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    city = forms.CharField(max_length=100)
    postal_code = forms.CharField(max_length=20, required=False)
    instructions = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)

    def clean_mobile_number(self) -> str:
        raw = self.cleaned_data["mobile_number"]
        normalized = normalize_pk_mobile(raw)
        if normalized is None:
            raise forms.ValidationError("Enter a valid Pakistani mobile number.")
        return normalized

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        if cleaned_data.get("same_as_mobile"):
            mobile_number = cleaned_data.get("mobile_number")
            if mobile_number:
                cleaned_data["whatsapp_number"] = mobile_number
            return cleaned_data

        raw_whatsapp = cleaned_data.get("whatsapp_number", "")
        if not raw_whatsapp:
            self.add_error("whatsapp_number", "Enter a WhatsApp number, or check “same as mobile”.")
            return cleaned_data
        normalized = normalize_pk_mobile(raw_whatsapp)
        if normalized is None:
            self.add_error("whatsapp_number", "Enter a valid Pakistani mobile number.")
        else:
            cleaned_data["whatsapp_number"] = normalized
        return cleaned_data


class OrderTrackingForm(AriaDescribedByMixin, StorefrontStyledFieldMixin, forms.Form):
    """Public order lookup (§25). Deliberately no ``clean_mobile_number``
    validation here — a malformed phone must fail the same generic way an
    order-not-found or a wrong-phone lookup does (``orders.tracking.
    lookup_order()`` owns that decision entirely), not surface as a
    third, distinguishable "invalid phone format" error that a real
    Pakistani mobile number would never trigger."""

    order_number = forms.CharField(max_length=20, label="Order number")
    mobile_number = forms.CharField(max_length=20, label="Mobile number")
