"""Roadmap Stage 12 gate 5: "No image renders without width and height
attributes" — automated the same way Stage 8 automated "no view reads
.variant.price" and Stage 10 automated "no template references
order.pk": scan every template source for the pattern gate 5 forbids,
rather than trust a one-time manual sweep to stay true as templates keep
changing.

Every ``<img>`` tag in this project, portal and storefront alike, is
required to carry explicit ``width``/``height`` attributes — the
CLS-prevention reason §36 cites applies just as much to the merchant
portal's own product thumbnails as to the storefront's.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_IMG_TAG_RE = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE | re.DOTALL)


def _template_files() -> list[Path]:
    return sorted((PROJECT_ROOT / "templates").rglob("*.html"))


def test_no_img_tag_is_missing_a_template_file() -> None:
    """The scan below is only meaningful if it's actually looking at
    real files — guards against a future ``templates/`` reorganisation
    silently making ``_template_files()`` return an empty list, which
    would make the real gate test below vacuously pass."""
    assert len(_template_files()) > 10


def test_gate5_every_img_tag_has_explicit_width_and_height_attributes() -> None:
    offenders: list[str] = []
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for match in _IMG_TAG_RE.finditer(text):
            tag = match.group(0)
            if "width=" not in tag or "height=" not in tag:
                line_number = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{line_number}: {tag.strip()}")
    assert offenders == [], "<img> tag(s) missing width/height:\n" + "\n".join(offenders)
