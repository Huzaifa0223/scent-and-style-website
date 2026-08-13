"""Pakistani mobile number normalisation to E.164 (§20) — hand-rolled
rather than a phone-number library, since the format is narrow and
well-defined (Pakistani mobile numbers only, not general international
numbers) and CLAUDE.md's approved dependency list has none.

Accepts ``03XXXXXXXXX`` (local, 11 digits), ``+923XXXXXXXXX`` or
``923XXXXXXXXX`` (already E.164-shaped), or the bare 10-digit
``3XXXXXXXXX`` local number with no prefix at all — all Pakistani mobile
numbers share the same 10-digit body starting with ``3`` (the trunk
prefix ``0`` and the country code ``92`` are just two different ways of
writing the same number), so one capture group handles every accepted
input shape.
"""

from __future__ import annotations

import re

_PK_MOBILE_RE = re.compile(r"^(?:\+92|92|0)?(3\d{9})$")


def normalize_pk_mobile(raw: str) -> str | None:
    """Returns the E.164 form (``+923XXXXXXXXX``), or ``None`` if ``raw``
    isn't a recognisable Pakistani mobile number."""
    cleaned = re.sub(r"[\s\-]", "", raw.strip())
    match = _PK_MOBILE_RE.match(cleaned)
    if match is None:
        return None
    return f"+92{match.group(1)}"
