"""Forms for the merchant order list/detail pages (roadmap Stage 10)."""

from __future__ import annotations

from decimal import Decimal

from django import forms

from catalog.models import ProductVariant
from core.forms import FIELD_CSS as _FIELD_CSS
from orders.models import Order

from .forms import _StyledModelForm


class OrderStatusTransitionForm(forms.Form):
    to_status = forms.ChoiceField(
        choices=Order.Status.choices, widget=forms.Select(attrs={"class": _FIELD_CSS})
    )
    note = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"class": _FIELD_CSS, "rows": 2})
    )


class OrderTrackingForm(_StyledModelForm[Order]):
    class Meta:
        model = Order
        fields = ["tracking_number", "courier_name", "merchant_notes"]
        widgets = {"merchant_notes": forms.Textarea(attrs={"rows": 3})}


class OrderLineQuantityForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1, widget=forms.NumberInput(attrs={"class": _FIELD_CSS})
    )


class OrderLinePriceForm(forms.Form):
    unit_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": _FIELD_CSS, "step": "0.01"}),
    )


class OrderLineAddForm(forms.Form):
    sku = forms.CharField(max_length=64, widget=forms.TextInput(attrs={"class": _FIELD_CSS}))
    quantity = forms.IntegerField(
        min_value=1, initial=1, widget=forms.NumberInput(attrs={"class": _FIELD_CSS})
    )

    def clean_sku(self) -> str:
        sku: str = self.cleaned_data["sku"].strip()
        try:
            variant = ProductVariant.objects.select_related("product").get(sku=sku)
        except ProductVariant.DoesNotExist as exc:
            raise forms.ValidationError(f"No variant with SKU {sku!r}.") from exc
        # Stashed here rather than re-queried in the view — clean_sku()
        # already paid for the lookup, and the view only ever calls this
        # after is_valid() has run it.
        self.cleaned_data["variant"] = variant
        return sku
