"""Shared, project-wide form behaviour — §37's ``aria-describedby``
wiring and the one input style every form in the project renders
through, so touch-target size and focus visibility are a property of
the base class, not something every new form has to remember to add.
"""

from __future__ import annotations

from typing import Any, Final

from django import forms

FIELD_CSS: Final[str] = (
    "mt-1 block min-h-11 w-full rounded border border-border-interactive bg-surface px-3 py-2 "
    "text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent"
)
CHECKBOX_CSS: Final[str] = (
    "h-5 w-5 rounded border-border-interactive text-accent focus:ring-2 focus:ring-accent"
)

# Storefront variant of the two constants above — same §37 requirements
# (44px touch target, visible focus ring), styled against the sf- dark
# editorial token set instead of the portal's light admin tokens. Kept
# separate rather than parameterising FIELD_CSS/CHECKBOX_CSS because the
# two token systems don't share values (see docs/design.md's Tailwind
# config section) and portal forms must never pick up storefront colours.
#
# These name .field/.checkbox component classes (static/css/input.css)
# rather than spelling out the utility strings, so a widget rendered by
# Django and a control written by hand in a template cannot drift apart.
# mt-1 stays here rather than inside .field: it is the gap between a label
# and its input, which only applies where a label precedes the field, and
# .field is also used by the filter rail's inline price inputs, which sit
# in a flex row with no label above them.
#
# tailwind.config.js scans this file — see the note on `content` there.
SF_FIELD_CSS: Final[str] = "field mt-1"
SF_CHECKBOX_CSS: Final[str] = "checkbox"


class StyledFieldMixin(forms.BaseForm):
    """Applies the project's one input style to every field automatically
    (§37): ``min-h-11`` (44px) satisfies the touch-target floor directly;
    ``focus:ring-2`` satisfies "focus states visible" without relying on
    each browser's own, often faint, default outline. One place, so a
    new form gets both for free rather than needing to remember either.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", CHECKBOX_CSS)
            else:
                field.widget.attrs.setdefault("class", FIELD_CSS)


class StorefrontStyledFieldMixin(forms.BaseForm):
    """Storefront counterpart to :class:`StyledFieldMixin` — identical
    §37 guarantees, styled against the sf- token set for forms that
    render on customer-facing pages (checkout, order tracking).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", SF_CHECKBOX_CSS)
            else:
                field.widget.attrs.setdefault("class", SF_FIELD_CSS)


class AriaDescribedByMixin(forms.BaseForm):
    """Sets ``aria-describedby="<field id>-error"`` on every field's
    widget, unconditionally — not only when the field currently has an
    error. The alternative (setting it only when ``field.errors`` is
    truthy) needs the *template* to also only conditionally render the
    element that id points to, which produces a dangling
    ``aria-describedby`` reference on any render where a field that
    previously errored no longer does. Always setting the attribute and
    always rendering the (possibly empty) error element it points to —
    see ``templates/orders/checkout.html``'s own error paragraph — avoids
    that dangling-reference case entirely, at the cost of one attribute
    on every field regardless of whether it's ever wrong.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name in self.fields:
            bound_field = self[name]
            self.fields[name].widget.attrs.setdefault(
                "aria-describedby", f"{bound_field.id_for_label}-error"
            )
