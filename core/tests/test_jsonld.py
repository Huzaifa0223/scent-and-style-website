"""core.templatetags.jsonld.ld_json — the project's single JSON-LD
serializer (§34, roadmap Stage 12). Mirrors test_money.py's own
directness: a filter this small gets a direct unit test, not just
indirect coverage through whatever page happens to render it.
"""

from __future__ import annotations

import json

from core.templatetags.jsonld import ld_json


def test_ld_json_serializes_a_dict_as_valid_json() -> None:
    data = {"@type": "Product", "name": "Test Product"}

    rendered = str(ld_json(data))

    assert json.loads(rendered) == data


def test_ld_json_escapes_script_breakout_characters() -> None:
    """A product name containing a literal </script> must not be able to
    break out of the <script type="application/ld+json"> tag it's
    rendered inside — the same protection Django's own json_script()
    applies, reimplemented here because json_script() hardcodes the
    wrong `type` attribute for JSON-LD (see this module's own docstring)."""
    data = {"name": "</script><script>alert(1)</script>"}

    rendered = str(ld_json(data))

    assert "</script>" not in rendered
    assert json.loads(rendered) == data


def test_ld_json_returns_an_empty_string_for_none() -> None:
    """storefront.seo.product_json_ld() can return None for a product
    with no variants — templates guard with {% if %} before
    ever passing None to this filter, but the filter itself stays
    defensive rather than raising if that guard is ever missed."""
    rendered = str(ld_json(None))

    assert rendered == ""
