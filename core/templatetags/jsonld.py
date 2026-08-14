"""The project's single JSON-LD serializer (§34) — mirrors money.py's own
reasoning: one canonical place, nothing in the project hand-rolls this
elsewhere.

Deliberately not Django's own ``json_script`` filter/function: that
helper hardcodes ``type="application/json"`` on the ``<script>`` tag it
renders, but search engines and rich-result validators specifically
require ``type="application/ld+json"`` to recognise structured data. This
filter applies the same ``<``/``>``/``&`` escaping ``json_script`` does
(so a product name or description containing a literal ``</script>``
can't break out of the tag) without inlining the ``<script>`` wrapper
itself — the caller writes ``<script type="application/ld+json">{{
data|ld_json }}</script>`` so the tag's attributes stay visible in the
template, not hidden inside a filter.
"""

from __future__ import annotations

import json
from typing import Any

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

_SCRIPT_BREAKOUT_ESCAPES = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}


@register.filter(name="ld_json", is_safe=True)
def ld_json(value: dict[str, Any] | None) -> SafeString:
    if value is None:
        return mark_safe("")
    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder).translate(_SCRIPT_BREAKOUT_ESCAPES))
